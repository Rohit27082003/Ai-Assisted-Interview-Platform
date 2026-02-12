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

from app.core.llm import get_llm, get_structured_llm
from app.schemas.outputs.evaluation_outputs import ReferenceAnswerOutput, RubricScoreOutput
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
    cheating_flags: List[Dict[str, Any]]


# ── Node Functions ────────────────────────────────────────────────

async def generate_references_node(state: EvaluationGraphState) -> EvaluationGraphState:
    """Generate reference answers for each question."""
    llm = get_structured_llm(ReferenceAnswerOutput)
    evaluations = []

    for entry in state["transcript_history"]:
        prompt_inputs = {
            "question": entry["question"],
            "pillar_name": entry.get("pillar", "General"),
            "job_role": state["jd_object"].get("role", "Candidate"),
            "depth_level": "3",  # Defaulting to 3 if not tracked per question in transcript
            "time_constraint": "45 seconds",
        }

        chain = REFERENCE_ANSWER_PROMPT | llm
        
        try:
            response: ReferenceAnswerOutput = await chain.ainvoke(prompt_inputs)
            reference_answer = response.reference_answer
            key_points = response.key_points
            advanced_points = response.advanced_points
            common_mistakes = response.common_mistakes
        except Exception as e:
            logger.error(f"Reference generation failed for {entry['question'][:20]}...: {e}")
            reference_answer = "Reference answer generation failed."
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
    """Score each Q/A pair using rubric scoring (1-5) with cheating penalties."""
    llm = get_structured_llm(RubricScoreOutput, temperature=0.1)
    scored_evaluations = []

    # Get cheating flags for penalty calculation
    cheating_flags = state.get("cheating_flags", [])
    cheating_flag_map = {flag.get("question_id"): flag for flag in cheating_flags if flag.get("question_id")}

    for eval_item in state["evaluations"]:
        prompt_inputs = {
            "question": eval_item["question"],
            "candidate_answer": eval_item["answer"],
            "reference_answer": eval_item["reference_answer"],
            "key_points": "\n- ".join(eval_item.get("key_points", [])),
            "advanced_points": "\n- ".join(eval_item.get("advanced_points", [])),
            "common_mistakes": "\n- ".join(eval_item.get("common_mistakes", [])),
        }

        chain = RUBRIC_SCORING_PROMPT | llm

        try:
            scores: RubricScoreOutput = await chain.ainvoke(prompt_inputs)
            
            # Extract scores from Pydantic model
            correctness = scores.correctness.score
            depth = scores.depth.score
            reasoning = scores.reasoning.score
            clarity = scores.clarity.score
            relevance = scores.relevance.score
            practical = scores.practical_application.score
            
            overall = scores.overall_score

            # Build comprehensive justification from all dimensions
            justification_parts = []
            for dim_name, dim_obj in [
                ("Correctness", scores.correctness),
                ("Depth", scores.depth),
                ("Reasoning", scores.reasoning),
                ("Clarity", scores.clarity),
                ("Relevance", scores.relevance),
                ("Practical Application", scores.practical_application),
            ]:
                if dim_obj.justification:
                    justification_parts.append(f"{dim_name} ({dim_obj.score}/5): {dim_obj.justification}")
            justification = " | ".join(justification_parts) if justification_parts else "No justification available."
            
            # Comparison metrics
            comparison = scores.expected_vs_actual_comparison
            similarity = scores.similarity_score

            # Apply cheating penalty if this question was flagged
            question_id = eval_item.get("question_id")
            cheating_penalty = 0.0
            cheating_note = ""

            if question_id and question_id in cheating_flag_map:
                flag = cheating_flag_map[question_id]
                severity = flag.get("severity", 0)

                # Calculate penalty: 0-30% reduction based on severity (0-10)
                penalty_percentage = (severity / 10.0) * 0.3  # Max 30% penalty
                cheating_penalty = overall * penalty_percentage
                overall = max(0.0, overall - cheating_penalty)

                # Also reduce individual scores proportionally
                penalty_factor = 1.0 - penalty_percentage
                correctness = max(0.0, correctness * penalty_factor)
                depth = max(0.0, depth * penalty_factor)
                reasoning = max(0.0, reasoning * penalty_factor)
                clarity = max(0.0, clarity * penalty_factor)
                relevance = max(0.0, relevance * penalty_factor)
                practical = max(0.0, practical * penalty_factor)

                cheating_note = f" [PENALTY: -{cheating_penalty:.1f} points, severity {severity:.1f}/10]"
                justification = f"{justification}{cheating_note}"
                logger.info(f"Applied cheating penalty: question_id={question_id}, penalty={cheating_penalty:.2f}")

            eval_item.update({
                "correctness": correctness,
                "depth": depth,
                "reasoning": reasoning,
                "clarity": clarity,
                "relevance": relevance,
                "practical_application": practical,
                "overall_score": overall,
                "justification": justification,
                "expected_vs_actual_comparison": comparison,
                "similarity_score": similarity,
                "cheating_penalty": cheating_penalty,
                "cheating_flagged": question_id in cheating_flag_map if question_id else False,
            })
        except Exception as e:
            logger.error(f"Rubric scoring failed: {e}")
            eval_item.update({
                "correctness": 3,
                "depth": 3,
                "reasoning": 3,
                "clarity": 3,
                "relevance": 3,
                "practical_application": 3,
                "overall_score": 3.0,
                "justification": "Scoring failed, default applied.",
                "expected_vs_actual_comparison": "Evaluation failed.",
                "similarity_score": 0.5,
                "cheating_penalty": 0.0,
                "cheating_flagged": False,
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
