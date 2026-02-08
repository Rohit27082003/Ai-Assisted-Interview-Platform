from datetime import datetime
from typing import Any, Dict, List, Optional
from .interview_state import InterviewState
from .enums import InterviewPhase, RouterDecision, CheatingLevel

def create_initial_state(
    interview_id: str,
    candidate_id: str,
    jd_id: str,
    candidate_name: str,
    candidate_email: str,
    job_role: str,
    job_requirements: Dict[str, Any],
    resume_context: str,
    focus_areas: List[Dict[str, str]],
    config: Optional[Dict[str, Any]] = None,
) -> InterviewState:
    """
    Factory function to create a properly initialized interview state.
    """
    config = config or {}
    now = datetime.utcnow()

    # Initialize focus areas with tracking fields
    initialized_focus_areas = [
        {
            "skill": fa["skill"],
            "reason": fa["reason"],
            "completed": False,
            "questions_asked": 0,
            "follow_ups_used": 0,
            "pillar_score": None,
        }
        for fa in focus_areas
    ]

    # Initialize timing state
    timing_state = {
        "reading_buffer_seconds": config.get("reading_buffer_seconds", 20),
        "answer_window_seconds": config.get("answer_window_seconds", 45),
        "question_displayed_at": None,
        "reading_deadline": None,
        "answer_started_at": None,
        "answer_deadline": None,
        "interview_started_at": now.isoformat(),
        "interview_timeout_minutes": config.get("interview_timeout_minutes", 60),
        "interview_deadline": None,
    }

    # Initialize termination conditions
    termination_conditions = {
        "all_pillars_completed": False,
        "hard_violation_detected": False,
        "violation_reason": None,
        "recruiter_terminated": False,
        "recruiter_termination_reason": None,
        "interview_timeout": False,
        "max_questions_reached": False,
    }

    return InterviewState(
        # Identity
        interview_id=interview_id,
        candidate_id=candidate_id,
        jd_id=jd_id,

        # Context
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        job_role=job_role,
        job_requirements=job_requirements,
        resume_context=resume_context,

        # Pillars
        focus_areas=initialized_focus_areas,
        current_pillar_index=0,
        total_pillars=len(initialized_focus_areas),

        # Current question
        current_question_id=None,
        current_question=None,
        current_question_depth=1,
        awaiting_answer=False,

        # Conversation memory
        message_history=[],
        question_records=[],

        # Analysis
        last_analysis_signals=None,
        cumulative_scores={},

        # Cheating
        cheating_flags=[],
        cheating_level=CheatingLevel.NONE.value,
        cheating_score=0.0,

        # Timing
        timing=timing_state,

        # Flow control
        phase=InterviewPhase.INITIALIZING.value,
        router_decision=RouterDecision.CONTINUE_PILLAR.value,
        termination_conditions=termination_conditions,

        # Counters
        total_questions_asked=0,
        total_follow_ups=0,
        questions_in_current_pillar=0,
        follow_ups_in_current_pillar=0,

        # Configuration
        max_questions_per_pillar=config.get("max_questions_per_pillar", 5),
        max_follow_ups_per_question=config.get("max_follow_ups_per_question", 2),
        max_total_questions=config.get("max_total_questions", 25),
        difficulty_progression_enabled=config.get("difficulty_progression_enabled", True),

        # Error handling
        error_count=0,
        last_error=None,

        # Observability
        transition_log=[],

        # Metadata
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        version=1,
    )


def log_transition(
    state: InterviewState,
    from_phase: str,
    to_phase: str,
    node_name: str,
    router_decision: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> InterviewState:
    """
    Add a transition log entry to state for observability.
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "from_phase": from_phase,
        "to_phase": to_phase,
        "node_name": node_name,
        "router_decision": router_decision,
        "details": details,
    }

    # Create new state with updated log
    new_log = state.get("transition_log", []) + [log_entry]
    return {**state, "transition_log": new_log, "updated_at": datetime.utcnow().isoformat()}


def get_current_pillar(state: InterviewState) -> Optional[Dict[str, Any]]:
    """Get the current focus area/pillar from state."""
    focus_areas = state.get("focus_areas", [])
    idx = state.get("current_pillar_index", 0)
    if 0 <= idx < len(focus_areas):
        return focus_areas[idx]
    return None


def get_conversation_context(state: InterviewState, max_messages: int = 10) -> List[Dict[str, str]]:
    """
    Extract recent conversation context for LLM prompts.
    Returns list of {"role": "assistant"|"human", "content": str}
    """
    question_records = state.get("question_records", [])
    context = []

    for record in question_records[-max_messages:]:
        context.append({
            "role": "assistant",
            "content": record.get("question_text", ""),
        })
        if record.get("answer_text"):
            context.append({
                "role": "human",
                "content": record.get("answer_text", ""),
            })

    return context


def update_pillar_score(state: InterviewState, pillar_index: int, score: float) -> InterviewState:
    """Update the cumulative score for a pillar."""
    cumulative_scores = state.get("cumulative_scores", {}).copy()
    focus_areas = state.get("focus_areas", [])

    if 0 <= pillar_index < len(focus_areas):
        pillar_name = focus_areas[pillar_index].get("skill", f"pillar_{pillar_index}")

        # Running average
        current_count = focus_areas[pillar_index].get("questions_asked", 0)
        current_score = cumulative_scores.get(pillar_name, 0.0)

        if current_count > 0:
            new_score = ((current_score * (current_count - 1)) + score) / current_count
        else:
            new_score = score

        cumulative_scores[pillar_name] = new_score

        # Update pillar's score
        new_focus_areas = focus_areas.copy()
        new_focus_areas[pillar_index] = {**focus_areas[pillar_index], "pillar_score": new_score}

        return {**state, "cumulative_scores": cumulative_scores, "focus_areas": new_focus_areas}

    return state
