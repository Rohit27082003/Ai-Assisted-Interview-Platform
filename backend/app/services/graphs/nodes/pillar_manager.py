"""
Pillar Manager Node

Manages topic/pillar progression in the interview.
Responsibilities:
- Initialize new pillars when transitioning
- Track pillar completion
- Reset per-pillar counters
- Generate transition messages

This node does NOT make routing decisions - only the router does that.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from app.schemas.state import (
    InterviewState,
    InterviewPhase,
    RouterDecision,
    log_transition,
    get_current_pillar,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


async def pillar_manager_node(state: InterviewState) -> Dict[str, Any]:
    """
    Manage pillar/topic progression.

    This node is called:
    1. At interview start to initialize the first pillar
    2. After router decision NEXT_PILLAR to transition to next topic
    3. After router decision END_* to finalize

    Args:
        state: Current interview state

    Returns:
        State updates (partial dict to merge)
    """
    router_decision = state.get("router_decision", RouterDecision.CONTINUE_PILLAR.value)
    current_phase = state.get("phase", InterviewPhase.INITIALIZING.value)
    current_idx = state.get("current_pillar_index", 0)
    focus_areas = state.get("focus_areas", [])

    logger.info(
        f"Pillar manager: phase={current_phase}, decision={router_decision}, "
        f"pillar_idx={current_idx}/{len(focus_areas)}"
    )

    updates: Dict[str, Any] = {}

    # Handle different scenarios
    if current_phase == InterviewPhase.INITIALIZING.value:
        # First time - initialize the interview
        updates = _initialize_interview(state)

    elif router_decision == RouterDecision.NEXT_PILLAR.value:
        # Transition to next pillar
        updates = _transition_to_next_pillar(state)

    elif router_decision in [
        RouterDecision.END_COMPLETE.value,
        RouterDecision.END_VIOLATION.value,
        RouterDecision.END_TIMEOUT.value,
        RouterDecision.END_RECRUITER.value,
    ]:
        # Interview ending - finalize current pillar
        updates = _finalize_interview(state, router_decision)

    else:
        # Normal flow - just update metadata
        updates = {
            "updated_at": datetime.utcnow().isoformat(),
        }

    # Log the transition
    if updates:
        new_phase = updates.get("phase", current_phase)
        updates = {
            **log_transition(
                {**state, **updates},
                from_phase=current_phase,
                to_phase=new_phase,
                node_name="pillar_manager",
                details={"action": _get_action_type(router_decision, current_phase)},
            ),
            **updates,
        }

    return updates


def _initialize_interview(state: InterviewState) -> Dict[str, Any]:
    """Initialize the interview with the first pillar."""
    focus_areas = state.get("focus_areas", [])

    if not focus_areas:
        logger.error("No focus areas defined for interview")
        return {
            "phase": InterviewPhase.TERMINATED.value,
            "last_error": "No focus areas defined",
        }

    first_pillar = focus_areas[0]
    logger.info(f"Initializing interview with pillar: {first_pillar.get('skill')}")

    return {
        "phase": InterviewPhase.QUESTIONING.value,
        "current_pillar_index": 0,
        "current_question_depth": 1,
        "questions_in_current_pillar": 0,
        "follow_ups_in_current_pillar": 0,
        "awaiting_answer": False,
        "updated_at": datetime.utcnow().isoformat(),
    }


def _transition_to_next_pillar(state: InterviewState) -> Dict[str, Any]:
    """Transition to the next pillar."""
    focus_areas = state.get("focus_areas", [])
    current_idx = state.get("current_pillar_index", 0)
    next_idx = current_idx + 1

    # Mark current pillar as complete
    updated_focus_areas = focus_areas.copy()
    if current_idx < len(updated_focus_areas):
        current = updated_focus_areas[current_idx].copy()
        current["completed"] = True
        updated_focus_areas[current_idx] = current

    if next_idx >= len(focus_areas):
        # No more pillars - this shouldn't happen as router should catch this
        logger.warning("Tried to transition past last pillar")
        return {
            "focus_areas": updated_focus_areas,
            "phase": InterviewPhase.COMPLETED.value,
        }

    next_pillar = focus_areas[next_idx]
    logger.info(
        f"Transitioning from pillar {current_idx} to {next_idx}: "
        f"{next_pillar.get('skill')}"
    )

    return {
        "focus_areas": updated_focus_areas,
        "current_pillar_index": next_idx,
        "current_question_depth": 1,  # Reset difficulty for new pillar
        "questions_in_current_pillar": 0,
        "follow_ups_in_current_pillar": 0,
        "phase": InterviewPhase.QUESTIONING.value,
        "router_decision": RouterDecision.CONTINUE_PILLAR.value,  # Reset for new pillar
        "updated_at": datetime.utcnow().isoformat(),
    }


def _finalize_interview(state: InterviewState, reason: str) -> Dict[str, Any]:
    """Finalize the interview."""
    focus_areas = state.get("focus_areas", [])
    current_idx = state.get("current_pillar_index", 0)

    # Mark current pillar as complete
    updated_focus_areas = focus_areas.copy()
    if current_idx < len(updated_focus_areas):
        current = updated_focus_areas[current_idx].copy()
        current["completed"] = True
        updated_focus_areas[current_idx] = current

    # Determine final phase
    if reason == RouterDecision.END_COMPLETE.value:
        final_phase = InterviewPhase.COMPLETED.value
    else:
        final_phase = InterviewPhase.TERMINATED.value

    logger.info(f"Finalizing interview: phase={final_phase}, reason={reason}")

    return {
        "focus_areas": updated_focus_areas,
        "phase": final_phase,
        "awaiting_answer": False,
        "updated_at": datetime.utcnow().isoformat(),
    }


def _get_action_type(router_decision: str, phase: str) -> str:
    """Get a human-readable action type for logging."""
    if phase == InterviewPhase.INITIALIZING.value:
        return "initialize"
    if router_decision == RouterDecision.NEXT_PILLAR.value:
        return "transition"
    if router_decision.startswith("end_"):
        return "finalize"
    return "update"


def get_pillar_summary(state: InterviewState) -> Dict[str, Any]:
    """
    Get a summary of the current pillar for context.

    Returns:
        Dict with pillar details for prompts
    """
    current_pillar = get_current_pillar(state)
    if not current_pillar:
        return {
            "pillar_name": "Unknown",
            "pillar_reason": "",
            "questions_asked": 0,
            "follow_ups_asked": 0,
        }

    return {
        "pillar_name": current_pillar.get("skill", "Unknown"),
        "pillar_reason": current_pillar.get("reason", ""),
        "questions_asked": current_pillar.get("questions_asked", 0),
        "follow_ups_asked": current_pillar.get("follow_ups_used", 0),
        "pillar_score": current_pillar.get("pillar_score"),
    }
