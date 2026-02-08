"""
State Schema Module

Exports the centralized interview state schema and utilities.
"""

from .enums import (
    InterviewPhase,
    RouterDecision,
    CheatingLevel,
    QuestionDepth,
)
from .models import (
    FocusArea,
    QuestionRecord,
    CheatingFlag,
    StateTransitionLog,
    TimingState,
    TerminationConditions,
)
from .interview_state import InterviewState
from .utils import (
    create_initial_state,
    log_transition,
    get_current_pillar,
    get_conversation_context,
    update_pillar_score,
)

__all__ = [
    # Enums
    "InterviewPhase",
    "RouterDecision",
    "CheatingLevel",
    "QuestionDepth",
    # Nested models
    "FocusArea",
    "QuestionRecord",
    "CheatingFlag",
    "StateTransitionLog",
    "TimingState",
    "TerminationConditions",
    # Main state
    "InterviewState",
    # Factory & utilities
    "create_initial_state",
    "log_transition",
    "get_current_pillar",
    "get_conversation_context",
    "update_pillar_score",
]
