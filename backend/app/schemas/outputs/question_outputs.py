"""
Structured Output Schemas for Question Generation

These schemas define the expected LLM output format for:
- Initial question generation
- Follow-up question generation
- Follow-up decision making
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class QuestionGenerationOutput(BaseModel):
    """
    Structured output for question generation.

    Used by the question_engine node to generate both initial
    and follow-up questions with proper typing.
    """

    question: str = Field(
        ...,
        description="The interview question to ask the candidate",
        min_length=10,
        max_length=1000,
    )

    question_type: str = Field(
        ...,
        description="Type of question: 'conceptual', 'practical', 'scenario', 'edge_case', 'expert'",
    )

    depth_level: int = Field(
        ...,
        description="Difficulty level from 1 (foundational) to 5 (expert)",
        ge=1,
        le=5,
    )

    target_skill: str = Field(
        ...,
        description="The specific skill or concept this question probes",
    )

    expected_coverage: List[str] = Field(
        default_factory=list,
        description="Key points a strong answer should cover",
    )

    time_estimate_seconds: int = Field(
        default=45,
        description="Estimated time to answer this question in seconds",
        ge=15,
        le=120,
    )

    probing_intent: str = Field(
        ...,
        description="What this question aims to discover about the candidate",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question": "Can you explain the difference between a process and a thread, and when you would choose one over the other?",
                "question_type": "conceptual",
                "depth_level": 2,
                "target_skill": "Operating Systems",
                "expected_coverage": [
                    "Definition of process vs thread",
                    "Memory sharing differences",
                    "Context switching overhead",
                    "Use cases for each",
                ],
                "time_estimate_seconds": 45,
                "probing_intent": "Assess fundamental OS knowledge and practical decision-making",
            }
        }


class FollowUpDecisionOutput(BaseModel):
    """
    Structured output for deciding whether to ask a follow-up.

    This is a rule-first decision with optional LLM assistance.
    The output determines the next action in the interview flow.
    """

    should_follow_up: bool = Field(
        ...,
        description="Whether a follow-up question should be asked",
    )

    reason: str = Field(
        ...,
        description="Explanation for the follow-up decision",
    )

    follow_up_type: Optional[str] = Field(
        default=None,
        description="Type of follow-up if applicable: 'clarification', 'deeper_probe', 'alternative_angle', 'verification'",
    )

    confidence: float = Field(
        default=0.8,
        description="Confidence in this decision from 0 to 1",
        ge=0,
        le=1,
    )

    follow_up_focus: Optional[str] = Field(
        default=None,
        description="What the follow-up should focus on",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "should_follow_up": True,
                "reason": "Candidate mentioned using mutex locks but didn't explain when deadlocks could occur",
                "follow_up_type": "deeper_probe",
                "confidence": 0.85,
                "follow_up_focus": "Deadlock conditions and prevention strategies",
            }
        }


class FollowUpQuestionOutput(BaseModel):
    """
    Structured output for generating a follow-up question.

    Follow-ups are targeted probes that don't change topics
    but explore depth in the current area.
    """

    follow_up_question: str = Field(
        ...,
        description="The follow-up question to ask",
        min_length=10,
        max_length=500,
    )

    builds_on: str = Field(
        ...,
        description="What aspect of the previous answer this builds on",
    )

    gap_addressed: str = Field(
        ...,
        description="What gap or unclear point this follow-up addresses",
    )

    expected_elaboration: List[str] = Field(
        default_factory=list,
        description="What the candidate should elaborate on",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "follow_up_question": "You mentioned using mutex locks. Can you walk me through a scenario where this could lead to a deadlock, and how would you prevent it?",
                "builds_on": "Candidate's mention of mutex locks for thread synchronization",
                "gap_addressed": "No discussion of potential deadlock scenarios",
                "expected_elaboration": [
                    "Deadlock conditions (circular wait, hold and wait, etc.)",
                    "Prevention strategies (lock ordering, timeouts)",
                    "Real-world example or debugging approach",
                ],
            }
        }
