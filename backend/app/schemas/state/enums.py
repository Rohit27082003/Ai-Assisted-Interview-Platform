from enum import Enum

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
