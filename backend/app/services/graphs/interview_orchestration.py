"""Graph 4 — Interview Orchestration Graph (CORE SYSTEM).

Event-driven interview flow:
  Select Pillar → Generate Question → Reading Timer → Audio Capture →
  Transcribe → Answer Understanding → Follow-up Generator

Repeat max 5 times per pillar, then auto-shift pillar.
Server-side timer enforcement.
"""

from typing import TypedDict, List, Dict, Any, Optional, Literal
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.llm import get_llm
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── Graph State ───────────────────────────────────────────────────

class InterviewGraphState(TypedDict):
    interview_id: str
    candidate_id: str
    jd_object: dict
    resume_text: str
    focus_areas: List[Dict[str, str]]
    current_pillar_index: int
    current_pillar: str
    question_number: int
    questions_in_pillar: int
    max_questions_per_pillar: int
    current_question: str
    current_answer: str
    is_follow_up: bool
    follow_up_count: int
    transcript_history: List[Dict[str, str]]
    pillar_complete: bool
    all_pillars_complete: bool
    next_action: str  # "generate_question", "process_answer", "follow_up", "next_pillar", "end"
    cheating_flags: List[Dict[str, Any]]


# ── Node Functions ────────────────────────────────────────────────

async def select_pillar_node(state: InterviewGraphState) -> InterviewGraphState:
    """Select the next focus area pillar for questioning."""
    focus_areas = state["focus_areas"]
    idx = state.get("current_pillar_index", 0)

    if idx >= len(focus_areas):
        state["all_pillars_complete"] = True
        state["next_action"] = "end"
        logger.info(f"All pillars completed for interview {state['interview_id']}")
        return state

    pillar = focus_areas[idx]
    state["current_pillar"] = pillar["skill"]
    state["current_pillar_index"] = idx
    state["questions_in_pillar"] = 0
    state["follow_up_count"] = 0
    state["pillar_complete"] = False
    state["next_action"] = "generate_question"

    logger.info(
        f"Interview {state['interview_id']}: Starting pillar '{pillar['skill']}' "
        f"({idx + 1}/{len(focus_areas)})"
    )
    return state


async def generate_question_node(state: InterviewGraphState) -> InterviewGraphState:
    """Generate an opening question for the current pillar."""
    llm = get_llm()

    # Build context from previous Q&As in this pillar
    pillar_history = [
        t for t in state.get("transcript_history", [])
        if t.get("pillar") == state["current_pillar"]
    ]
    history_text = ""
    for t in pillar_history:
        history_text += f"Q: {t['question']}\nA: {t['answer']}\n\n"

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a senior technical interviewer conducting a live interview.

Topic/Pillar: {pillar}
Job Role: {role}
Candidate's background: {resume_summary}

{history_section}

Generate a single, clear, open-ended technical question about {pillar}.
The question should:
- Test deep understanding, not surface knowledge
- Be answerable in 45 seconds of speaking
- Be progressively harder if previous questions were answered well
- NOT repeat any previously asked question

Return ONLY the question text, nothing else."""),
        ("human", "Generate the next interview question."),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({
        "pillar": state["current_pillar"],
        "role": state["jd_object"].get("role", ""),
        "resume_summary": state["resume_text"][:2000],
        "history_section": f"Previous Q&As in this topic:\n{history_text}" if history_text else "This is the first question on this topic.",
    })

    state["current_question"] = response.content.strip()
    state["question_number"] = state.get("question_number", 0) + 1
    state["questions_in_pillar"] = state.get("questions_in_pillar", 0) + 1
    state["is_follow_up"] = False
    state["next_action"] = "await_answer"

    logger.info(
        f"Interview {state['interview_id']}: Q{state['question_number']} "
        f"on '{state['current_pillar']}'"
    )
    return state


async def answer_understanding_node(state: InterviewGraphState) -> InterviewGraphState:
    """Analyze the candidate's answer for understanding and completeness."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are analyzing an interview answer.

Question: {question}
Topic: {pillar}

Evaluate the answer on:
1. Did they actually answer the question?
2. Is the answer technically correct?
3. How deep is their understanding?
4. Are there gaps that should be probed with a follow-up?

Return ONLY a JSON object:
{{
  "answered": true/false,
  "correctness": "high"/"medium"/"low",
  "depth": "deep"/"moderate"/"shallow",
  "needs_followup": true/false,
  "followup_reason": "why a follow-up is needed (or empty string)",
  "key_points": ["list of key points they mentioned"]
}}
Do not include any markdown formatting."""),
        ("human", "Answer: {answer}"),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({
        "question": state["current_question"],
        "pillar": state["current_pillar"],
        "answer": state["current_answer"],
    })

    import json
    try:
        analysis = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        analysis = {"answered": True, "needs_followup": False}

    # Record in transcript history
    state.setdefault("transcript_history", []).append({
        "pillar": state["current_pillar"],
        "question": state["current_question"],
        "answer": state["current_answer"],
        "analysis": analysis,
        "is_follow_up": state.get("is_follow_up", False),
    })

    # Decide next action
    max_q = state.get("max_questions_per_pillar", settings.MAX_QUESTIONS_PER_TOPIC)
    questions_so_far = state.get("questions_in_pillar", 1)
    follow_ups = state.get("follow_up_count", 0)

    if questions_so_far >= max_q:
        state["pillar_complete"] = True
        state["next_action"] = "next_pillar"
    elif analysis.get("needs_followup") and follow_ups < 2:
        state["next_action"] = "follow_up"
    elif questions_so_far < max_q:
        state["next_action"] = "generate_question"
    else:
        state["pillar_complete"] = True
        state["next_action"] = "next_pillar"

    logger.info(
        f"Interview {state['interview_id']}: Answer analyzed, next={state['next_action']}"
    )
    return state


async def followup_generator_node(state: InterviewGraphState) -> InterviewGraphState:
    """Generate a targeted follow-up question based on the previous answer."""
    llm = get_llm()

    last_entry = state["transcript_history"][-1] if state.get("transcript_history") else {}
    analysis = last_entry.get("analysis", {})

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a senior interviewer asking a follow-up question.

Original question: {original_question}
Candidate's answer: {answer}
Topic: {pillar}
Follow-up reason: {followup_reason}

Generate a targeted follow-up that:
- Probes the specific gap or shallow area in their answer
- Is concise and focused
- Tests deeper understanding

Return ONLY the follow-up question, nothing else."""),
        ("human", "Generate follow-up question."),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({
        "original_question": state["current_question"],
        "answer": state["current_answer"],
        "pillar": state["current_pillar"],
        "followup_reason": analysis.get("followup_reason", "Needs deeper exploration"),
    })

    state["current_question"] = response.content.strip()
    state["is_follow_up"] = True
    state["follow_up_count"] = state.get("follow_up_count", 0) + 1
    state["question_number"] = state.get("question_number", 0) + 1
    state["questions_in_pillar"] = state.get("questions_in_pillar", 0) + 1
    state["next_action"] = "await_answer"

    logger.info(
        f"Interview {state['interview_id']}: Follow-up Q{state['question_number']} "
        f"on '{state['current_pillar']}'"
    )
    return state


async def shift_pillar_node(state: InterviewGraphState) -> InterviewGraphState:
    """Move to the next pillar."""
    state["current_pillar_index"] = state.get("current_pillar_index", 0) + 1
    state["pillar_complete"] = False
    state["questions_in_pillar"] = 0
    state["follow_up_count"] = 0

    if state["current_pillar_index"] >= len(state["focus_areas"]):
        state["all_pillars_complete"] = True
        state["next_action"] = "end"
    else:
        state["next_action"] = "select_pillar"

    logger.info(f"Interview {state['interview_id']}: Shifting to next pillar")
    return state


async def end_interview_node(state: InterviewGraphState) -> InterviewGraphState:
    """Finalize the interview session."""
    state["all_pillars_complete"] = True
    state["next_action"] = "end"
    logger.info(
        f"Interview {state['interview_id']}: Completed. "
        f"Total questions: {state.get('question_number', 0)}"
    )
    return state


# ── Routing Function ──────────────────────────────────────────────

def route_interview(state: InterviewGraphState) -> str:
    """Route to the next node based on interview state."""
    action = state.get("next_action", "end")
    if action == "generate_question":
        return "generate_question"
    elif action == "follow_up":
        return "followup_generator"
    elif action == "next_pillar":
        return "shift_pillar"
    elif action == "select_pillar":
        return "select_pillar"
    elif action == "end":
        return "end_interview"
    return "end_interview"


# ── Build Graph ───────────────────────────────────────────────────

def build_interview_graph() -> StateGraph:
    """Build and compile the Interview Orchestration Graph.

    NOTE: This graph is designed to be stepped through, not run to completion.
    The "await_answer" state pauses execution until an answer is submitted.
    """
    graph = StateGraph(InterviewGraphState)

    graph.add_node("select_pillar", select_pillar_node)
    graph.add_node("generate_question", generate_question_node)
    graph.add_node("answer_understanding", answer_understanding_node)
    graph.add_node("followup_generator", followup_generator_node)
    graph.add_node("shift_pillar", shift_pillar_node)
    graph.add_node("end_interview", end_interview_node)

    graph.set_entry_point("select_pillar")

    graph.add_edge("select_pillar", "generate_question")
    # After generate_question, we pause (return to caller for audio capture)
    graph.add_edge("generate_question", END)

    # After answer is processed, route to next step
    graph.add_conditional_edges(
        "answer_understanding",
        route_interview,
        {
            "generate_question": "generate_question",
            "follow_up": "followup_generator",
            "next_pillar": "shift_pillar",
            "end_interview": "end_interview",
        }
    )

    # Follow-up returns a new question, pause for answer
    graph.add_edge("followup_generator", END)

    # Shift pillar routes based on state
    graph.add_conditional_edges(
        "shift_pillar",
        route_interview,
        {
            "select_pillar": "select_pillar",
            "end_interview": "end_interview",
        }
    )

    graph.add_edge("end_interview", END)

    return graph.compile()
