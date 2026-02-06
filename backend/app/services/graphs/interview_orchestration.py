"""Graph 4 — Production Interview Orchestration (CORE SYSTEM).

Architecture:
   ENTRY
     ↓
   pillar_manager (State Update)
     ↓
   question_engine (Generates Question)
     ↓
   interrupt(await_audio) (Pauses for User Input)
     ↓
   audio_pipeline (Processes Input)
     ↓
   answer_analyzer (Evaluates Answer)
     ↓
   decision_router (Logic Unit) → Loop or End

This graph prioritizes state correctness and deterministic execution.
"""

from typing import TypedDict, List, Dict, Any, Optional, Literal, Union
from typing_extensions import Annotated
import operator
from datetime import datetime

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.core.llm import get_llm
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ── State Schema ──────────────────────────────────────────────────────

class InterviewState(TypedDict):
    # --- Context (Static/Config) ---
    interview_id: str
    candidate_id: str
    job_role: str
    resume_context: str  # Summarized text
    
    # --- Progression State ---
    focus_areas: List[Dict[str, str]]  # Content of pillars
    current_pillar_index: int          # 0 -> N
    current_pillar: str                # e.g. "React"
    pillar_results: Dict[str, Any]     # Storage for scores/notes per pillar
    
    # --- Conversation State (Mutable) ---
    # We append messages to history. 
    # Annotated[list, operator.add] means new updates extend the list.
    message_history: Annotated[List[BaseMessage], operator.add]
    
    current_question: Optional[str]
    current_question_depth: int  # 1=Foundational, 3=Deep, 5=Expert
    
    # Inputs from User (injected on resume)
    current_answer_text: Optional[str]
    
    # --- Signals & Routing (Ephemeral) ---
    analysis_signals: Dict[str, Any]  # Output of Analyzer
    router_decision: str              # "next_question", "follow_up", "next_pillar", "end"
    
    # --- Safety & Metrics ---
    error_count: int
    cheating_score: float
    question_count_in_pillar: int


def get_initial_state() -> InterviewState:
    """Helper to produce a clean initial state."""
    return {
        "interview_id": "",
        "candidate_id": "",
        "job_role": "",
        "resume_context": "",
        "focus_areas": [],
        "current_pillar_index": -1,  # Start before first
        "current_pillar": "",
        "pillar_results": {},
        "message_history": [],
        "current_question": None,
        "current_question_depth": 1,
        "current_answer_text": None,
        "analysis_signals": {},
        "router_decision": "start",
        "error_count": 0,
        "cheating_score": 0.0,
        "question_count_in_pillar": 0,
    }


# ── Nodes ─────────────────────────────────────────────────────────────

async def pillar_manager_node(state: InterviewState) -> InterviewState:
    """Manages high-level topic progression and depth state."""
    idx = state.get("current_pillar_index", -1)
    focus_areas = state.get("focus_areas", [])
    router_decision = state.get("router_decision", "start")
    
    updates = {}
    
    # Case: First run or explicit "next_pillar" command
    if router_decision in ["start", "next_pillar"]:
        next_idx = idx + 1
        
        if next_idx >= len(focus_areas):
            # No more pillars
            logger.info(f"Interview {state.get('interview_id')}: All pillars complete.")
            return {"router_decision": "end"}
        
        # Initialize new pillar
        new_pillar = focus_areas[next_idx]
        pillar_name = new_pillar.get("skill", "General")
        
        updates.update({
            "current_pillar_index": next_idx,
            "current_pillar": pillar_name,
            "current_question_depth": 1,         # Reset depth
            "question_count_in_pillar": 0,       # Reset count
            "router_decision": "continue"        # Clear signal
        })
        
        logger.info(f"Starting Pillar: {pillar_name} ({next_idx + 1}/{len(focus_areas)})")
    
    # Case: Same pillar, just incrementing depth/count logic is handled by router/question engine
    # but we sanity check here if needed.
    
    return updates


async def question_engine_node(state: InterviewState) -> InterviewState:
    """Generates the next question based on current depth and history."""
    llm = get_llm()
    
    pillar = state["current_pillar"]
    role = state["job_role"]
    resume = state["resume_context"]
    depth = state["current_question_depth"]
    history = state["message_history"][-6:] # Keep context window reasonable
    decision = state.get("router_decision", "next_question")
    
    # Identify if follow-up
    is_followup = (decision == "follow_up")
    
    system_prompt = f"""You are an expert technical interviewer for a {role} position.
Current Topic: {pillar}
Target Difficulty: Level {depth}/5
"""
    
    if is_followup:
        input_prompt = """The candidate's previous answer had gaps or was interesting.
Generate a targeted FOLLOW-UP question to dig deeper.
- Be concise.
- Probe specific claims.
- Do not change topics.
"""
    else:
        # Pre-calculate difficulty description
        difficulty_map = {
            1: "Foundational",
            2: "Foundational/Practical",
            3: "Practical/Scenario", 
            4: "Scenario/Edge Case",
            5: "Expert/Edge Case"
        }
        diff_desc = difficulty_map.get(depth, "Practical")
        
        input_prompt = f"""Generate a NEW question for this topic.
- Level {{depth}}: {diff_desc}
- If Level 1-2: Ask about core concepts.
- If Level 3-4: Ask for a specific scenario or trade-off.
- If Level 5: Ask about system internals or complex failure modes.
- Context: Use the candidate's background if relevant.
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("placeholder", "{messages}"),
        ("human", input_prompt)
    ])
    
    chain = prompt | llm
    
    # We pass the history so the LLM sees previous Q&A
    response = await chain.ainvoke({
        "messages": history,
        "depth": depth
    })
    
    question_text = response.content.strip()
    
    # Update state
    return {
        "current_question": question_text,
        "message_history": [AIMessage(content=question_text)], # Appends to history
        "question_count_in_pillar": state["question_count_in_pillar"] + 1
    }


async def audio_pipeline_node(state: InterviewState) -> InterviewState:
    """Captures the answer. In this design, it processes the text injected during resume."""
    # Assuming 'current_answer_text' was provided during graph.resume() or update_state
    answer_text = state.get("current_answer_text")
    
    if not answer_text:
        # Fallback if empty (e.g. timeout or silence)
        answer_text = "(No answer detected)"
    
    logger.info(f"Processing Answer: {answer_text[:50]}...")
    
    return {
        "message_history": [HumanMessage(content=answer_text)]
    }


async def answer_analyzer_node(state: InterviewState) -> InterviewState:
    """Evaluates the answer for correctness, depth, and red flags."""
    llm = get_llm()
    
    question = state.get("current_question", "Unknown Question")
    answer = state.get("current_answer_text", "")
    pillar = state.get("current_pillar", "General")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an answer auditor. 
Evaluate the candidate's response to: "{question}" (Topic: {pillar}).

Output JSON ONLY:
{{
  "is_relevant": bool,      # Did they try to answer?
  "correctness_score": int, # 1-10
  "depth_score": int,       # 1-5 (5=Deep Insight)
  "missing_concepts": [],   # List of strings
  "followup_suggested": bool, # True if gaps need probing OR answer was fascinating
  "cheating_suspicion": int # 0-10 (10=Robot/Read from screen)
}}"""),
        ("human", f"Candidate Answer: {answer}")
    ])
    
    try:
        response = await (prompt | llm).ainvoke({"question": question, "pillar": pillar, "answer": answer})
        import json
        signals = json.loads(response.content)
    except Exception:
        logger.error("Failed to parse analysis JSON, using fallback.")
        signals = {
            "is_relevant": True, 
            "correctness_score": 5, 
            "depth_score": 3,
            "followup_suggested": False,
            "cheating_suspicion": 0
        }
    
    return {
        "analysis_signals": signals,
        "cheating_score": max(state.get("cheating_score", 0), signals.get("cheating_suspicion", 0))
    }


async def decision_router_node(state: InterviewState) -> InterviewState:
    """The Brain. Decides the next move based on rules + analysis signals."""
    signals = state.get("analysis_signals", {})
    q_count = state.get("question_count_in_pillar", 0)
    current_depth = state.get("current_question_depth", 1)
    
    # 1. Safety/Termination Rules
    if state.get("cheating_score", 0) > 8:
        logger.warning(f"Cheating detected ({state['cheating_score']}). Ending.")
        return {"router_decision": "end"}

    # 2. Pillar limits
    MAX_Q_PER_PILLAR = settings.MAX_QUESTIONS_PER_TOPIC or 5
    if q_count >= MAX_Q_PER_PILLAR:
        return {"router_decision": "next_pillar"}
    
    # 3. Logic Flow
    # If answer was poor or irrelevant, maybe retry? or just move on if mostly ok?
    # For now, if irrelevant but not cheating, we might just ask next question.
    
    decision = "next_question"
    new_depth = current_depth
    
    if signals.get("followup_suggested") and q_count < MAX_Q_PER_PILLAR - 1:
        # Only follow up if we have room
        decision = "follow_up"
        # Depth stays same or increases slightly for the follow up
    else:
        # Move to next question, increase difficulty if they did well
        if signals.get("correctness_score", 0) >= 7:
            new_depth = min(5, current_depth + 1)
        decision = "next_question"

    return {
        "router_decision": decision,
        "current_question_depth": new_depth
    }


# ── Routing Logic ─────────────────────────────────────────────────────

def route_manager(state: InterviewState) -> str:
    """Determines where the graph goes after decision_router."""
    decision = state.get("router_decision", "end")
    
    if decision == "end":
        return "end"
    elif decision == "next_pillar":
        return "pillar_manager"
    elif decision in ["next_question", "follow_up"]:
        return "question_engine"
    
    return "end"


# ── Graph Construction ────────────────────────────────────────────────

def build_interview_graph(checkpointer: Optional[Any] = None) -> Any:
    """Builds the production-grade interview graph.
    
    Args:
        checkpointer: Optional persistence layer (e.g. MemorySaver, AsyncPostgresSaver).
    """
    graph = StateGraph(InterviewState)
    
    # Add Nodes
    graph.add_node("pillar_manager", pillar_manager_node)
    graph.add_node("question_engine", question_engine_node)
    graph.add_node("audio_pipeline", audio_pipeline_node)
    graph.add_node("answer_analyzer", answer_analyzer_node)
    graph.add_node("decision_router", decision_router_node)
    
    # Set Entry
    graph.set_entry_point("pillar_manager")
    
    # Edges
    
    # 1. Manager -> Question (if continue) OR End (if done)
    # We use a conditional edge here because Manager might decide "All Pillars Done"
    def route_from_manager(state):
        if state.get("router_decision") == "end":
            return END
        return "question_engine"
    
    graph.add_conditional_edges("pillar_manager", route_from_manager)
    
    # 2. Question -> Interrupt -> Audio
    # In LangGraph, we can just point to audio_pipeline, but we adding an interrupt_before
    # at the runtime level. For the edges, it's just a direct link.
    graph.add_edge("question_engine", "audio_pipeline")
    
    # 3. Audio -> Analyzer
    graph.add_edge("audio_pipeline", "answer_analyzer")
    
    # 4. Analyzer -> Router
    graph.add_edge("answer_analyzer", "decision_router")
    
    # 5. Router -> (Cycle or End)
    graph.add_conditional_edges(
        "decision_router", 
        route_manager,
        {
            "pillar_manager": "pillar_manager",
            "question_engine": "question_engine",
            "end": END
        }
    )
    
    return graph.compile(checkpointer=checkpointer, interrupt_before=["audio_pipeline"])
