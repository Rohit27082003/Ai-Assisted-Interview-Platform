"""
Audio Pipeline Node

Processes candidate audio input and transcription.
Responsibilities:
- Receive transcribed answer text
- Store audio to S3 (async)
- Update message history
- Enforce timing constraints (server-side)

This node does NOT analyze content - that's answer_analyzer's job.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

from app.schemas.state import (
    InterviewState,
    InterviewPhase,
)
from app.core.logging import get_logger
from app.utils.datetime_helpers import parse_iso_datetime

logger = get_logger(__name__)


def _update_question_record(
    records: list, question_id: str, updates: Dict[str, Any]
) -> list:
    """Update a specific question record by question_id, returning a new list."""
    updated = records.copy()
    for i, record in enumerate(updated):
        if record.get("question_id") == question_id:
            updated[i] = {**record, **updates}
            break
    return updated


async def audio_pipeline_node(
    state: InterviewState,
    answer_text: Optional[str] = None,
    audio_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process candidate's answer input.

    This node is invoked after the graph is resumed with candidate input.
    It receives the transcribed answer and updates state accordingly.

    Args:
        state: Current interview state
        answer_text: Transcribed answer text (injected on resume)
        audio_url: S3 URL for audio file (optional)

    Returns:
        State updates with answer recorded
    """
    current_question_id = state.get("current_question_id")
    timing = state.get("timing", {})

    logger.info(
        f"Audio pipeline: question_id={current_question_id}, "
        f"answer_length={len(answer_text) if answer_text else 0}"
    )

    # Validate timing (server-side enforcement)
    timing_violation = _check_timing_violation(timing)
    if timing_violation:
        logger.warning(f"Timing violation: {timing_violation}")
        # We still process but flag it

    # Calculate time used
    now = datetime.now(timezone.utc)
    question_displayed_at = timing.get("question_displayed_at")
    answer_started_at = timing.get("answer_started_at")

    reading_time_used = None
    answer_time_used = None

    if question_displayed_at:
        displayed_at = parse_iso_datetime(question_displayed_at)

        total_time = (now - displayed_at).total_seconds()
        reading_buffer = timing.get("reading_buffer_seconds", 20)

        if answer_started_at:
            started_at = parse_iso_datetime(answer_started_at)
            reading_time_used = (started_at - displayed_at).total_seconds()
            answer_time_used = (now - started_at).total_seconds()
        else:
            # Assume reading took the minimum of buffer or total time
            reading_time_used = min(reading_buffer, total_time)
            answer_time_used = max(0, total_time - reading_time_used)

    # Update the question record with answer
    updated_records = _update_question_record(
        state.get("question_records", []),
        current_question_id,
        {
            "answer_text": answer_text,
            "answer_audio_url": audio_url,
            "answer_received_at": now.isoformat(),
            "reading_time_used": reading_time_used,
            "answer_time_used": answer_time_used,
        },
    )

    # Add to message history
    message_history = []
    if answer_text:
        message_history = [HumanMessage(content=answer_text)]

    updates = {
        "question_records": updated_records,
        "message_history": message_history,  # Annotated list will append
        "awaiting_answer": False,
        "phase": InterviewPhase.ANALYZING.value,
        "updated_at": now.isoformat(),
    }

    # Clear timing for next question
    updated_timing = timing.copy()
    updated_timing["answer_received_at"] = now.isoformat()
    updates["timing"] = updated_timing

    logger.info(
        f"Answer recorded: {len(answer_text) if answer_text else 0} chars, "
        f"reading_time={reading_time_used:.1f}s, answer_time={answer_time_used:.1f}s"
        if reading_time_used and answer_time_used else "Answer recorded"
    )

    return updates


def _check_timing_violation(timing: Dict[str, Any]) -> Optional[str]:
    """
    Check if timing constraints were violated.

    Returns:
        Violation message if violated, None otherwise
    """
    answer_deadline = timing.get("answer_deadline")
    if not answer_deadline:
        return None

    now = datetime.now(timezone.utc)

    deadline = parse_iso_datetime(answer_deadline)

    if now > deadline:
        overtime = (now - deadline).total_seconds()
        return f"Answer submitted {overtime:.1f}s past deadline"

    return None
