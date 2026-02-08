"""Graph 5 — Evaluation Graph.

Runs AFTER interview ends.
For each Q/A:
  1. Generate reference answer using LLM
  2. Score across: correctness, depth, reasoning, clarity (1-5 rubric)
  3. Return structured JSON only
"""

from typing import TypedDict, List, Dict, Any
import json
from langgraph.graph import StateGraph, END

from app.prompts import (
    REFERENCE_ANSWER_PROMPT,
    RUBRIC_SCORING_PROMPT,
)

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
        prompt_inputs = {
            "question": entry["question"],
            "pillar_name": entry.get("pillar", "General"),
            "job_role": state["jd_object"].get("role", "Candidate"),
            "depth_level": "3",  # Defaulting to 3 if not tracked per question in transcript
            "time_constraint": "45 seconds",
        }

        response = await REFERENCE_ANSWER_PROMPT.ainvoke(prompt_inputs)
        
        try:
            ref_data = json.loads(response.content)
            reference_answer = ref_data.get("reference_answer", "")
            key_points = ref_data.get("key_points", [])
            advanced_points = ref_data.get("advanced_points", [])
            common_mistakes = ref_data.get("common_mistakes", [])
        except (json.JSONDecodeError, AttributeError):
            # Fallback if specific JSON parsing fails
            reference_answer = response.content.strip()
            key_points = []
            advanced_points = []
            common_mistakes = []

        evaluations.append({
            "pillar": entry.get("pillar", "General"),
            "question": entry["question"],
            "answer": entry.get("answer", ""),
            "reference_answer": reference_answer,
            "key_points": key_points,
            "advanced_points": advanced_points,
            "common_mistakes": common_mistakes,
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
        prompt_inputs = {
            "question": eval_item["question"],
            "candidate_answer": eval_item["answer"],
            "reference_answer": eval_item["reference_answer"],
            "key_points": "\n- ".join(eval_item.get("key_points", [])),
            "advanced_points": "\n- ".join(eval_item.get("advanced_points", [])),
            "common_mistakes": "\n- ".join(eval_item.get("common_mistakes", [])),
        }

        response = await RUBRIC_SCORING_PROMPT.ainvoke(prompt_inputs)

        try:
            scores = json.loads(response.content)
            # Handle potentially different structure if prompt changed, 
            # ideally prompt returns "correctness": {"score": 5, ...} but we need to be robust.
            # The prompt defines: "correctness": { "score": 1-5, ... }
            
            def get_score(dim):
                val = scores.get(dim)
                if isinstance(val, dict):
                    return int(val.get("score", 3))
                return int(val) if val else 3

            correctness = get_score("correctness")
            depth = get_score("depth")
            reasoning = get_score("reasoning")
            clarity = get_score("clarity")
            
            overall = float(scores.get("overall_score", 0))
            if overall == 0:
                 overall = round((correctness + depth + reasoning + clarity) / 4, 2)

            eval_item.update({
                "correctness": correctness,
                "depth": depth,
                "reasoning": reasoning,
                "clarity": clarity,
                "overall_score": overall,
                "justification": str(scores.get("correctness", {}).get("justification", "See details")), # Simplified justification handling
            })
        except (json.JSONDecodeError, AttributeError, ValueError, TypeError):
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
