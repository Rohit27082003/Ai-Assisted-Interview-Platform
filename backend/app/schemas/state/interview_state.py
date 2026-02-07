"""
Centralized Interview State Schema

This module defines the single source of truth for interview state.
All graph nodes read from and write to this state structure.
State is persisted in PostgreSQL JSONB for resumability.
"""

from __future__ import annotations

import operator
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class InterviewPhase(str, Enum):
    """Current phase of the interview lifecycle."""
    INITIALIZING = "initializing"
    QUESTIONING = "questioning"
    AWAITING_ANSWER = "awaiting_answer"
    ANALYZING = "analyzing"
    TRANSITIONING = "transitioning"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class RouterDecision(str, Enum):
    """Deterministic decisions from the decision router."""
    CONTINUE_PILLAR = "continue_pillar"      # Generate next question in same pillar
    FOLLOW_UP = "follow_up"                   # Generate follow-up question
    NEXT_PILLAR = "next_pillar"               # Move to next pillar/topic
    END_COMPLETE = "end_complete"             # All pillars completed normally
    END_VIOLATION = "end_violation"           # Hard violation detected
    END_TIMEOUT = "end_timeout"               # Interview timeout
    END_RECRUITER = "end_recruiter"           # Recruiter terminated
    AWAIT_INPUT = "await_input"               # Waiting for candidate input


class CheatingLevel(str, Enum):
    """Cheating escalation levels."""
    NONE = "none"
    WARNING_1 = "warning_1"
    WARNING_2 = "warning_2"
    PENALTY = "penalty"  # Results in termination


class QuestionDepth(int, Enum):
    """Question difficulty levels (1-5)."""
    FOUNDATIONAL = 1
    PRACTICAL = 2
    SCENARIO = 3
    EDGE_CASE = 4
    EXPERT = 5


# ═══════════════════════════════════════════════════════════════════════════════
# NESTED STATE MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class FocusArea(BaseModel):
    """A single focus area/pillar for the interview."""
    skill: str = Field(..., description="The skill or topic to probe")
    reason: str = Field(..., description="Why this area needs probing")
    completed: bool = Field(default=False, description="Whether this pillar is complete")
    questions_asked: int = Field(default=0, description="Questions asked in this pillar")
    follow_ups_used: int = Field(default=0, description="Follow-ups used in this pillar")
    pillar_score: Optional[float] = Field(default=None, description="Aggregate score for pillar")


class QuestionRecord(BaseModel):
    """Record of a single question-answer exchange."""
    question_id: str = Field(..., description="Unique identifier for this Q&A")
    pillar_index: int = Field(..., description="Index of the pillar this belongs to")
    pillar_name: str = Field(..., description="Name of the pillar")
    question_text: str = Field(..., description="The question asked")
    question_depth: int = Field(..., description="Difficulty level 1-5")
    is_follow_up: bool = Field(default=False, description="Whether this was a follow-up")

    # Answer details (populated after candidate responds)
    answer_text: Optional[str] = Field(default=None, description="Candidate's answer")
    answer_audio_url: Optional[str] = Field(default=None, description="S3 URL for audio")

    # Timing
    question_sent_at: Optional[datetime] = Field(default=None)
    answer_received_at: Optional[datetime] = Field(default=None)
    reading_time_used: Optional[float] = Field(default=None, description="Seconds used for reading")
    answer_time_used: Optional[float] = Field(default=None, description="Seconds used for answering")

    # Evaluation signals (populated after analysis)
    evaluation_signals: Optional[Dict[str, Any]] = Field(default=None)


class CheatingFlag(BaseModel):
    """A single cheating detection flag."""
    question_id: str = Field(..., description="Question this flag relates to")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reason: str = Field(..., description="Why this was flagged")
    severity: float = Field(..., ge=0, le=10, description="Severity score 0-10")
    details: Optional[Dict[str, Any]] = Field(default=None)


class StateTransitionLog(BaseModel):
    """Log entry for state transitions (observability)."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    from_phase: str
    to_phase: str
    node_name: str
    router_decision: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════════════════════
# TIMING STATE
# ═══════════════════════════════════════════════════════════════════════════════


class TimingState(BaseModel):
    """Server-side timing control state."""
    reading_buffer_seconds: int = Field(default=20, description="Time allowed to read question")
    answer_window_seconds: int = Field(default=45, description="Time allowed to answer")

    # Current question timing
    question_displayed_at: Optional[datetime] = Field(default=None)
    reading_deadline: Optional[datetime] = Field(default=None)
    answer_started_at: Optional[datetime] = Field(default=None)
    answer_deadline: Optional[datetime] = Field(default=None)

    # Interview-level timing
    interview_started_at: Optional[datetime] = Field(default=None)
    interview_timeout_minutes: int = Field(default=60)
    interview_deadline: Optional[datetime] = Field(default=None)


# ═══════════════════════════════════════════════════════════════════════════════
# TERMINATION CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════════


class TerminationConditions(BaseModel):
    """
    Guarded conditions for interview termination.
    Only the decision router can trigger termination by evaluating these.
    """
    all_pillars_completed: bool = Field(default=False)
    hard_violation_detected: bool = Field(default=False)
    violation_reason: Optional[str] = Field(default=None)
    recruiter_terminated: bool = Field(default=False)
    recruiter_termination_reason: Optional[str] = Field(default=None)
    interview_timeout: bool = Field(default=False)
    max_questions_reached: bool = Field(default=False)

    def should_terminate(self) -> tuple[bool, RouterDecision]:
        """
        Evaluate termination conditions in priority order.
        Returns (should_terminate, reason).
        """
        if self.hard_violation_detected:
            return True, RouterDecision.END_VIOLATION
        if self.recruiter_terminated:
            return True, RouterDecision.END_RECRUITER
        if self.interview_timeout:
            return True, RouterDecision.END_TIMEOUT
        if self.all_pillars_completed:
            return True, RouterDecision.END_COMPLETE
        return False, RouterDecision.CONTINUE_PILLAR


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN INTERVIEW STATE
# ═══════════════════════════════════════════════════════════════════════════════


class InterviewState(TypedDict, total=False):
    """
    The single, strongly-typed interview state schema.

    This state is:
    - Persisted in PostgreSQL JSONB via LangGraph checkpointing
    - The single source of truth for all graph nodes
    - Resumable after failures
    - Fully observable for debugging

    All graph transitions are state-based. Nodes mutate and return state.
    No node can directly end the interview - only the decision router can.
    """

    # ─── Identity ─────────────────────────────────────────────────────────────
    interview_id: str
    candidate_id: str
    jd_id: str

    # ─── Context (Immutable after init) ───────────────────────────────────────
    candidate_name: str
    candidate_email: str
    job_role: str
    job_requirements: Dict[str, Any]  # Parsed JD object
    resume_context: str  # Extracted resume text

    # ─── Pillars/Focus Areas ──────────────────────────────────────────────────
    focus_areas: List[Dict[str, Any]]  # List of FocusArea dicts
    current_pillar_index: int
    total_pillars: int

    # ─── Current Question State ───────────────────────────────────────────────
    current_question_id: Optional[str]
    current_question: Optional[str]
    current_question_depth: int  # 1-5
    awaiting_answer: bool

    # ─── Conversation Memory ──────────────────────────────────────────────────
    # Annotated list for LangGraph append-only semantics
    message_history: Annotated[List[BaseMessage], operator.add]

    # Full question-answer records for context and persistence
    question_records: List[Dict[str, Any]]  # List of QuestionRecord dicts

    # ─── Analysis Signals ─────────────────────────────────────────────────────
    last_analysis_signals: Optional[Dict[str, Any]]
    cumulative_scores: Dict[str, float]  # Pillar -> cumulative score

    # ─── Cheating Detection ───────────────────────────────────────────────────
    cheating_flags: List[Dict[str, Any]]  # List of CheatingFlag dicts
    cheating_level: str  # CheatingLevel enum value
    cheating_score: float  # 0-10 cumulative

    # ─── Timing ───────────────────────────────────────────────────────────────
    timing: Dict[str, Any]  # TimingState dict

    # ─── Flow Control ─────────────────────────────────────────────────────────
    phase: str  # InterviewPhase enum value
    router_decision: str  # RouterDecision enum value
    termination_conditions: Dict[str, Any]  # TerminationConditions dict

    # ─── Counters ─────────────────────────────────────────────────────────────
    total_questions_asked: int
    total_follow_ups: int
    questions_in_current_pillar: int
    follow_ups_in_current_pillar: int

    # ─── Configuration ────────────────────────────────────────────────────────
    max_questions_per_pillar: int
    max_follow_ups_per_question: int
    max_total_questions: int
    difficulty_progression_enabled: bool

    # ─── Error Handling ───────────────────────────────────────────────────────
    error_count: int
    last_error: Optional[str]

    # ─── Observability ────────────────────────────────────────────────────────
    transition_log: List[Dict[str, Any]]  # List of StateTransitionLog dicts

    # ─── Metadata ─────────────────────────────────────────────────────────────
    created_at: str  # ISO timestamp
    updated_at: str  # ISO timestamp
    version: int  # For optimistic locking


# ═══════════════════════════════════════════════════════════════════════════════
# STATE FACTORY
# ═══════════════════════════════════════════════════════════════════════════════


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

    Args:
        interview_id: UUID of the interview
        candidate_id: UUID of the candidate
        jd_id: UUID of the job description
        candidate_name: Name of the candidate
        candidate_email: Email of the candidate
        job_role: Title of the job role
        job_requirements: Parsed JD object with skills, competencies, etc.
        resume_context: Extracted resume text
        focus_areas: List of {"skill": str, "reason": str} dicts
        config: Optional configuration overrides

    Returns:
        Initialized InterviewState ready for the graph
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


# ═══════════════════════════════════════════════════════════════════════════════
# STATE UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════


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
