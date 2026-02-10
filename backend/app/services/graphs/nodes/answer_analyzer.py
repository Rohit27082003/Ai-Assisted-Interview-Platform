"""
Answer Analyzer Node

Analyzes candidate answers and produces evaluation signals.
Responsibilities:
- Analyze answer quality (structured output)
- Detect cheating patterns (structured output)
- Update cumulative scores
- Generate follow-up indicators

This node does NOT control flow - it only produces signals.
The decision_router uses these signals to make routing decisions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.llm import get_llm
from app.schemas.state import (
    InterviewState,
    InterviewPhase,
    CheatingLevel,
    get_current_pillar,
    update_pillar_score,
)
from app.schemas.outputs.analysis_outputs import (
    AnswerAnalysisOutput,
    CheatingDetectionOutput,
)
from app.prompts import (
    ANSWER_ANALYSIS_PROMPT,
    CHEATING_DETECTION_PROMPT,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


# Cheating escalation thresholds
CHEATING_THRESHOLDS = {
    "warning_1": 4.0,
    "warning_2": 6.0,
    "penalty": 8.0,
}


async def answer_analyzer_node(state: InterviewState) -> Dict[str, Any]:
    """
    Analyze the candidate's answer and produce evaluation signals.

    This node:
    1. Runs answer quality analysis (structured LLM output)
    2. Runs cheating detection (structured LLM output)
    3. Updates cumulative scores
    4. Produces signals for the router

    Args:
        state: Current interview state

    Returns:
        State updates with analysis signals
    """
    question_records = state.get("question_records", [])
    if not question_records:
        logger.warning("No question records to analyze")
        return {"phase": InterviewPhase.QUESTIONING.value}

    # Get the last question/answer pair
    last_record = question_records[-1]
    question = last_record.get("question_text", "")
    answer = last_record.get("answer_text", "")

    if not answer or answer.startswith("[TIMEOUT") or answer == "(No answer provided)":
        logger.info("No answer to analyze (timeout or empty)")
        # Create empty signals indicating no response
        signals = {
            "is_relevant": False,
            "correctness_score": 0.0,
            "depth_score": 0.0,
            "clarity_score": 0.0,
            "overall_signal_score": 0.0,
            "has_probeable_gaps": False,
            "analysis_summary": "No answer provided",
        }

        # KEY FIX: Update question_records to reflect the empty answer
        updated_records = question_records.copy()
        updated_records[-1] = {
            **last_record,
            "answer_text": answer or "(No answer provided)",
            "evaluation_signals": signals,
        }

        return {
            "question_records": updated_records,
            "last_analysis_signals": signals,
            "phase": InterviewPhase.QUESTIONING.value,
            "updated_at": datetime.utcnow().isoformat(),
        }

    current_pillar = get_current_pillar(state)
    pillar_name = current_pillar.get("skill", "Unknown") if current_pillar else "Unknown"

    logger.info(f"Analyzing answer for question in pillar: {pillar_name}")

    try:
        # Run analysis and cheating detection in parallel
        analysis_output, cheating_output = await _run_parallel_analysis(
            state, question, answer, pillar_name
        )

        # Convert to signal dict
        signals = {
            "is_relevant": analysis_output.is_relevant,
            "relevance_score": analysis_output.relevance_score,
            "correctness_score": analysis_output.correctness_score,
            "depth_score": analysis_output.depth_score,
            "clarity_score": analysis_output.clarity_score,
            "key_concepts_covered": analysis_output.key_concepts_covered,
            "missing_concepts": analysis_output.missing_concepts,
            "misconceptions": analysis_output.misconceptions,
            "has_probeable_gaps": analysis_output.has_probeable_gaps,
            "suggested_probe_areas": analysis_output.suggested_probe_areas,
            "overall_signal_score": analysis_output.overall_signal_score,
            "analysis_summary": analysis_output.analysis_summary,
        }

        # Update question record with evaluation signals
        updated_records = question_records.copy()
        updated_records[-1] = {
            **last_record,
            "evaluation_signals": signals,
        }

        # Process cheating detection
        cheating_updates = _process_cheating_signals(state, cheating_output, last_record)

        # Update pillar score
        current_idx = state.get("current_pillar_index", 0)
        state_with_score = update_pillar_score(state, current_idx, analysis_output.overall_signal_score)

        # Determine difficulty adjustment
        difficulty_adjustment = _calculate_difficulty_adjustment(analysis_output)
        new_depth = state.get("current_question_depth", 1)
        if state.get("difficulty_progression_enabled", True):
            new_depth = max(1, min(5, new_depth + difficulty_adjustment))

        updates = {
            "question_records": updated_records,
            "last_analysis_signals": signals,
            "cumulative_scores": state_with_score.get("cumulative_scores", {}),
            "focus_areas": state_with_score.get("focus_areas", []),
            "current_question_depth": new_depth,
            "phase": InterviewPhase.QUESTIONING.value,
            "updated_at": datetime.utcnow().isoformat(),
            **cheating_updates,
        }

        logger.info(
            f"Analysis complete: score={analysis_output.overall_signal_score:.1f}, "
            f"gaps={analysis_output.has_probeable_gaps}, "
            f"cheating_level={cheating_updates.get('cheating_level', 'none')}"
        )

        return updates

    except Exception as e:
        logger.error(f"Answer analysis failed: {e}", exc_info=True)
        # Return safe defaults on error
        return {
            "last_analysis_signals": {
                "is_relevant": True,
                "overall_signal_score": 5.0,
                "has_probeable_gaps": False,
                "analysis_summary": "Analysis error - defaulting to neutral",
            },
            "error_count": state.get("error_count", 0) + 1,
            "last_error": str(e),
            "phase": InterviewPhase.QUESTIONING.value,
            "updated_at": datetime.utcnow().isoformat(),
        }


async def _run_parallel_analysis(
    state: InterviewState,
    question: str,
    answer: str,
    pillar_name: str,
) -> tuple[AnswerAnalysisOutput, CheatingDetectionOutput]:
    """Run answer analysis and cheating detection in parallel."""
    import asyncio

    current_pillar = get_current_pillar(state)
    depth_level = state.get("current_question_depth", 1)

    # Get expected coverage from question record if available
    question_records = state.get("question_records", [])
    expected_coverage = []
    if question_records:
        last_record = question_records[-1]
        expected_coverage = last_record.get("expected_coverage", [])

    expected_coverage_str = "\n".join(f"- {c}" for c in expected_coverage) if expected_coverage else "Not specified"

    # Build prompt inputs for analysis
    analysis_inputs = {
        "question": question,
        "answer": answer,
        "pillar_name": pillar_name,
        "expected_coverage": expected_coverage_str,
        "depth_level": str(depth_level),
        "time_taken_seconds": "45",
        "is_follow_up": str(question_records[-1].get("is_follow_up", False)).lower() if question_records else "false",
    }

    question_number = state.get("total_questions_asked", 1)
    previous_quality = _get_previous_answer_quality(state)

    # Build prompt inputs for cheating detection
    cheating_inputs = {
        "question": question,
        "answer": answer,
        "question_number": str(question_number),
        "previous_answer_quality": previous_quality,
        "time_to_respond_seconds": "30",
        "candidate_demonstrated_level": _estimate_candidate_level(state),
    }

    llm = get_llm()

    # Run both in parallel
    analysis_task = llm.with_structured_output(AnswerAnalysisOutput).ainvoke(ANSWER_ANALYSIS_PROMPT.format(**analysis_inputs))
    cheating_task = llm.with_structured_output(CheatingDetectionOutput).ainvoke(CHEATING_DETECTION_PROMPT.format(**cheating_inputs))

    analysis_output, cheating_output = await asyncio.gather(analysis_task, cheating_task)

    return analysis_output, cheating_output


def _process_cheating_signals(
    state: InterviewState,
    cheating_output: CheatingDetectionOutput,
    question_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Process cheating detection output and update state."""
    current_score = state.get("cheating_score", 0.0)
    current_level = state.get("cheating_level", CheatingLevel.NONE.value)
    existing_flags = state.get("cheating_flags", [])

    updates: Dict[str, Any] = {}

    # Check for question repetition - this is a high-severity violation
    if cheating_output.question_repetition_detected or cheating_output.question_repetition_score >= 7.0:
        logger.warning(f"Question repetition detected: score={cheating_output.question_repetition_score}")
        # Add extra penalty for question repetition
        severity_boost = 2.0
        cheating_output.suspicion_score = min(10.0, cheating_output.suspicion_score + severity_boost)
        if "Question repetition detected" not in cheating_output.pattern_flags:
            cheating_output.pattern_flags.append("Question repetition instead of answering")
        cheating_output.is_suspicious = True

    if cheating_output.is_suspicious:
        # Add new flag
        new_flag = {
            "question_id": question_record.get("question_id"),
            "timestamp": datetime.utcnow().isoformat(),
            "reason": cheating_output.reasoning,
            "severity": cheating_output.suspicion_score,
            "question_repetition": cheating_output.question_repetition_detected,
            "details": {
                "pattern_flags": cheating_output.pattern_flags,
                "question_repetition_score": cheating_output.question_repetition_score,
                "parroting_score": cheating_output.question_parroting_score,
                "fluency_score": cheating_output.unnatural_fluency_score,
                "timing_flag": cheating_output.response_timing_flag,
                "vocabulary_mismatch": cheating_output.vocabulary_mismatch,
                "external_help": cheating_output.external_help_indicators,
            },
        }
        updated_flags = existing_flags + [new_flag]

        # Update cumulative score (weighted average with recency bias)
        new_score = (current_score * 0.7) + (cheating_output.suspicion_score * 0.3)
        new_score = min(10.0, new_score)

        # Determine escalation
        old_level = current_level
        new_level = current_level
        if new_score >= CHEATING_THRESHOLDS["penalty"]:
            new_level = CheatingLevel.PENALTY.value
        elif new_score >= CHEATING_THRESHOLDS["warning_2"]:
            new_level = CheatingLevel.WARNING_2.value
        elif new_score >= CHEATING_THRESHOLDS["warning_1"]:
            new_level = CheatingLevel.WARNING_1.value

        updates = {
            "cheating_flags": updated_flags,
            "cheating_score": new_score,
            "cheating_level": new_level,
        }

        # Store warning message if level escalated (to be sent to candidate)
        if new_level != old_level and new_level != CheatingLevel.NONE.value:
            warning_message = _get_warning_message(new_level, cheating_output)
            updates["_pending_warning_message"] = warning_message
            logger.info(f"Cheating warning prepared: {new_level}")

        # Check for hard violation
        if new_level == CheatingLevel.PENALTY.value:
            term_conditions = state.get("termination_conditions", {}).copy()
            term_conditions["hard_violation_detected"] = True
            term_conditions["violation_reason"] = f"Cheating penalty level reached: {cheating_output.reasoning}"
            updates["termination_conditions"] = term_conditions

        logger.warning(
            f"Cheating flag: score={new_score:.1f}, level={new_level}, "
            f"reason={cheating_output.reasoning[:50]}"
        )

    return updates


def _calculate_difficulty_adjustment(analysis: AnswerAnalysisOutput) -> int:
    """Calculate difficulty adjustment based on analysis."""
    score = analysis.overall_signal_score

    if score >= 7.5:
        return 1  # Increase difficulty
    elif score <= 4.0:
        return -1  # Decrease difficulty

    return 0  # Maintain


def _get_previous_answer_quality(state: InterviewState) -> str:
    """Estimate quality of previous answers for cheating detection context."""
    question_records = state.get("question_records", [])
    if len(question_records) < 2:
        return "no_previous"

    previous_signals = question_records[-2].get("evaluation_signals", {})
    if not previous_signals:
        return "unknown"

    score = previous_signals.get("overall_signal_score", 5.0)
    if score >= 7.5:
        return "high"
    elif score >= 5.0:
        return "moderate"
    else:
        return "low"


def _estimate_candidate_level(state: InterviewState) -> str:
    """Estimate candidate's demonstrated level from cumulative scores."""
    cumulative = state.get("cumulative_scores", {})
    if not cumulative:
        return "unknown"

    avg_score = sum(cumulative.values()) / len(cumulative)
    if avg_score >= 7.5:
        return "advanced"
    elif avg_score >= 5.5:
        return "intermediate"
    else:
        return "beginner"


def _get_warning_message(cheating_level: str, cheating_output: CheatingDetectionOutput) -> str:
    """Generate appropriate warning message based on cheating level."""
    if cheating_level == CheatingLevel.WARNING_1.value:
        return (
            "⚠️ First Warning: Please ensure you are answering in your own words without external assistance. "
            "We've detected patterns that may indicate misconduct."
        )
    elif cheating_level == CheatingLevel.WARNING_2.value:
        return (
            "⚠️⚠️ Second Warning: We have detected multiple instances of concerning behavior. "
            "Further violations will result in immediate interview termination. "
            "Please answer questions independently and in your own words."
        )
    elif cheating_level == CheatingLevel.PENALTY.value:
        return (
            "❌ Final Warning: Your interview has been flagged for serious misconduct. "
            "This interview may be terminated or heavily penalized in evaluation."
        )
    else:
        return "Please continue answering questions honestly and independently."
