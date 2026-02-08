from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from .enums import RouterDecision

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
