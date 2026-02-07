"""
Structured Output Schemas for Answer Analysis

These schemas define the expected LLM output format for:
- Answer analysis and evaluation signals
- Cheating detection signals
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AnswerAnalysisOutput(BaseModel):
    """
    Structured output for answer analysis.

    Used by the answer_analyzer node to convert transcripts
    into structured evaluation signals. This node does NOT
    control flow - it only produces signals for the router.
    """

    # Relevance assessment
    is_relevant: bool = Field(
        ...,
        description="Whether the answer addresses the question asked",
    )

    relevance_score: float = Field(
        ...,
        description="How well the answer addresses the question (0-10)",
        ge=0,
        le=10,
    )

    # Quality scores
    correctness_score: float = Field(
        ...,
        description="Factual accuracy of the answer (0-10)",
        ge=0,
        le=10,
    )

    depth_score: float = Field(
        ...,
        description="Technical depth demonstrated (0-10)",
        ge=0,
        le=10,
    )

    clarity_score: float = Field(
        ...,
        description="Clarity and structure of explanation (0-10)",
        ge=0,
        le=10,
    )

    # Content analysis
    key_concepts_covered: List[str] = Field(
        default_factory=list,
        description="Important concepts the candidate correctly addressed",
    )

    missing_concepts: List[str] = Field(
        default_factory=list,
        description="Important concepts the candidate missed or got wrong",
    )

    misconceptions: List[str] = Field(
        default_factory=list,
        description="Any incorrect statements or misunderstandings",
    )

    # Follow-up indicators (signals, not decisions)
    has_probeable_gaps: bool = Field(
        default=False,
        description="Whether there are gaps worth probing with a follow-up",
    )

    suggested_probe_areas: List[str] = Field(
        default_factory=list,
        description="Areas that could benefit from follow-up questions",
    )

    # Composite score for routing decisions
    overall_signal_score: float = Field(
        ...,
        description="Weighted composite score for routing (0-10)",
        ge=0,
        le=10,
    )

    # Brief analysis for logging
    analysis_summary: str = Field(
        ...,
        description="One-sentence summary of the answer quality",
        max_length=200,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "is_relevant": True,
                "relevance_score": 8.5,
                "correctness_score": 7.0,
                "depth_score": 6.0,
                "clarity_score": 8.0,
                "key_concepts_covered": [
                    "Process vs thread memory isolation",
                    "Context switching overhead",
                ],
                "missing_concepts": [
                    "Inter-process communication mechanisms",
                    "Thread safety considerations",
                ],
                "misconceptions": [],
                "has_probeable_gaps": True,
                "suggested_probe_areas": [
                    "IPC mechanisms and when to use them",
                    "Thread synchronization primitives",
                ],
                "overall_signal_score": 7.1,
                "analysis_summary": "Solid foundational understanding with room to probe synchronization knowledge",
            }
        }


class CheatingDetectionOutput(BaseModel):
    """
    Structured output for cheating detection.

    This analyzes answer patterns for signs of:
    - Copy-pasting from external sources
    - Reading from prepared scripts
    - Using AI assistants
    - Question parroting
    """

    # Overall flag
    is_suspicious: bool = Field(
        ...,
        description="Whether the answer shows suspicious patterns",
    )

    suspicion_score: float = Field(
        ...,
        description="Overall suspicion level (0-10, higher = more suspicious)",
        ge=0,
        le=10,
    )

    # Specific indicators
    pattern_flags: List[str] = Field(
        default_factory=list,
        description="Specific suspicious patterns detected",
    )

    # Individual checks
    question_parroting_score: float = Field(
        default=0.0,
        description="How much the answer mirrors the question (0-10)",
        ge=0,
        le=10,
    )

    unnatural_fluency_score: float = Field(
        default=0.0,
        description="Unnaturally polished/formatted answer (0-10)",
        ge=0,
        le=10,
    )

    response_timing_flag: bool = Field(
        default=False,
        description="Whether response timing suggests reading/copying",
    )

    vocabulary_mismatch: bool = Field(
        default=False,
        description="Whether vocabulary doesn't match candidate's level",
    )

    # Analysis
    confidence: float = Field(
        default=0.5,
        description="Confidence in the cheating assessment (0-1)",
        ge=0,
        le=1,
    )

    reasoning: str = Field(
        ...,
        description="Explanation of the cheating assessment",
        max_length=300,
    )

    # Recommendation (not a decision - router decides)
    recommended_action: str = Field(
        default="continue",
        description="Recommended action: 'continue', 'warn', 'flag', 'escalate'",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "is_suspicious": True,
                "suspicion_score": 6.5,
                "pattern_flags": [
                    "Unusually comprehensive for time allowed",
                    "Contains technical jargon not in previous answers",
                ],
                "question_parroting_score": 2.0,
                "unnatural_fluency_score": 7.0,
                "response_timing_flag": True,
                "vocabulary_mismatch": True,
                "confidence": 0.7,
                "reasoning": "Answer quality significantly exceeds previous responses and contains terminology inconsistent with demonstrated knowledge level",
                "recommended_action": "warn",
            }
        }


class CheatingEscalationOutput(BaseModel):
    """
    Structured output for cheating escalation decisions.

    Used when cumulative cheating signals exceed thresholds.
    """

    current_level: str = Field(
        ...,
        description="Current cheating level: 'none', 'warning_1', 'warning_2', 'penalty'",
    )

    escalate_to: Optional[str] = Field(
        default=None,
        description="Level to escalate to, if any",
    )

    should_terminate: bool = Field(
        default=False,
        description="Whether interview should be terminated",
    )

    termination_reason: Optional[str] = Field(
        default=None,
        description="Reason for termination if applicable",
    )

    cumulative_evidence: List[str] = Field(
        default_factory=list,
        description="Summary of accumulated cheating evidence",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "current_level": "warning_1",
                "escalate_to": "warning_2",
                "should_terminate": False,
                "termination_reason": None,
                "cumulative_evidence": [
                    "Question 3: High parroting score (8.2)",
                    "Question 5: Vocabulary mismatch detected",
                ],
            }
        }
