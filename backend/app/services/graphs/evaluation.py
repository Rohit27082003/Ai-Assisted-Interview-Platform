"""Graph 5 — Evaluation Graph.

Runs AFTER interview ends.
For each Q/A:
  1. Generate reference answer using LLM
  2. Score across: correctness, depth, reasoning, clarity (1-5 rubric)
  3. Return structured JSON only
"""

from typing import TypedDict, List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.llm import get_llm
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Graph State ───────────────────────────────────────────────────

class EvaluationGraphState(TypedDict):
    interview_id: str
    candidate_id: str
    jd_object: dict
    transcript_history: List[Dict[str, Any]]
    evaluations: List[Dict[str, Any]]
    average_score: float
    pillar_scores: Dict[str, float]


# ── Node Functions ────────────────────────────────────────────────

async def generate_references_node(state: EvaluationGraphState) -> EvaluationGraphState:
    """Generate reference answers for each question."""
    llm = get_llm()
    evaluations = []

    for entry in state["transcript_history"]:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a technical expert. Generate a comprehensive reference answer
for this interview question.

Topic: {pillar}
Role context: {role}

The reference answer should be what a strong candidate would say in 45 seconds.
Be concise but thorough. Return ONLY the reference answer text."""),
            ("human", "Question: {question}"),
        ])
        chain = prompt | llm
        response = await chain.ainvoke({
            "pillar": entry.get("pillar", "General"),
            "role": state["jd_object"].get("role", ""),
            "question": entry["question"],
        })

        evaluations.append({
            "pillar": entry.get("pillar", "General"),
            "question": entry["question"],
            "answer": entry.get("answer", ""),
            "reference_answer": response.content.strip(),
            "is_follow_up": entry.get("is_follow_up", False),
        })

    state["evaluations"] = evaluations
    logger.info(f"Generated {len(evaluations)} reference answers for interview {state['interview_id']}")
    return state


async def rubric_scoring_node(state: EvaluationGraphState) -> EvaluationGraphState:
    """Score each Q/A pair using rubric scoring (1-5)."""
    llm = get_llm(temperature=0.1)
    scored_evaluations = []

    for eval_item in state["evaluations"]:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an objective interview evaluator using a strict rubric.

Score the candidate's answer against the reference answer on these dimensions (1-5 each):

RUBRIC:
- correctness: 1=Wrong, 2=Mostly wrong, 3=Partially correct, 4=Mostly correct, 5=Fully correct
- depth: 1=Surface only, 2=Shallow, 3=Moderate depth, 4=Good depth, 5=Expert depth
- reasoning: 1=No reasoning, 2=Weak logic, 3=Some reasoning, 4=Good reasoning, 5=Excellent logical flow
- clarity: 1=Incoherent, 2=Unclear, 3=Understandable, 4=Clear, 5=Exceptionally clear

Question: {question}
Reference Answer: {reference_answer}
Candidate Answer: {candidate_answer}

Return ONLY a JSON:
{{
  "correctness": <1-5>,
  "depth": <1-5>,
  "reasoning": <1-5>,
  "clarity": <1-5>,
  "justification": "2-3 sentence explanation of scores"
}}
Do not include any markdown formatting."""),
            ("human", "Score this answer."),
        ])
        chain = prompt | llm
        response = await chain.ainvoke({
            "question": eval_item["question"],
            "reference_answer": eval_item["reference_answer"],
            "candidate_answer": eval_item["answer"],
        })

        import json
        try:
            scores = json.loads(response.content)
            correctness = int(scores.get("correctness", 3))
            depth = int(scores.get("depth", 3))
            reasoning = int(scores.get("reasoning", 3))
            clarity = int(scores.get("clarity", 3))
            overall = round((correctness + depth + reasoning + clarity) / 4, 2)

            eval_item.update({
                "correctness": correctness,
                "depth": depth,
                "reasoning": reasoning,
                "clarity": clarity,
                "overall_score": overall,
                "justification": scores.get("justification", ""),
            })
        except (json.JSONDecodeError, AttributeError, ValueError):
            eval_item.update({
                "correctness": 3,
                "depth": 3,
                "reasoning": 3,
                "clarity": 3,
                "overall_score": 3.0,
                "justification": "Scoring failed, default applied.",
            })

        scored_evaluations.append(eval_item)

    state["evaluations"] = scored_evaluations
    logger.info(f"Rubric scoring complete for interview {state['interview_id']}")
    return state


async def aggregate_scores_node(state: EvaluationGraphState) -> EvaluationGraphState:
    """Aggregate per-question scores into pillar scores and overall average."""
    pillar_scores: Dict[str, List[float]] = {}
    all_scores = []

    for ev in state["evaluations"]:
        score = ev.get("overall_score", 0)
        pillar = ev.get("pillar", "General")
        pillar_scores.setdefault(pillar, []).append(score)
        all_scores.append(score)

    # Average per pillar
    state["pillar_scores"] = {
        pillar: round(sum(scores) / len(scores), 2)
        for pillar, scores in pillar_scores.items()
    }

    # Overall average
    state["average_score"] = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0

    logger.info(
        f"Evaluation aggregated for interview {state['interview_id']}: "
        f"avg={state['average_score']}, pillars={state['pillar_scores']}"
    )
    return state


# ── Build Graph ───────────────────────────────────────────────────

def build_evaluation_graph() -> StateGraph:
    """Build and compile the Evaluation Graph."""
    graph = StateGraph(EvaluationGraphState)

    graph.add_node("generate_references", generate_references_node)
    graph.add_node("rubric_scoring", rubric_scoring_node)
    graph.add_node("aggregate_scores", aggregate_scores_node)

    graph.set_entry_point("generate_references")
    graph.add_edge("generate_references", "rubric_scoring")
    graph.add_edge("rubric_scoring", "aggregate_scores")
    graph.add_edge("aggregate_scores", END)

    return graph.compile()
