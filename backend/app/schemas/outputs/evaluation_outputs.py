"""
Structured Output Schemas for Post-Interview Evaluation

These schemas define the expected LLM output format for:
- Reference answer generation
- Rubric-based scoring
- Aggregate evaluation metrics
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ReferenceAnswerOutput(BaseModel):
    """
    Structured output for generating reference answers.

    Reference answers establish what a strong candidate would say,
    enabling objective scoring against a benchmark.
    """

    reference_answer: str = Field(
        ...,
        description="What a strong candidate would answer in 45 seconds",
        min_length=50,
        max_length=1500,
    )

    key_points: List[str] = Field(
        ...,
        description="Essential points a good answer must cover",
        min_length=2,
    )

    advanced_points: List[str] = Field(
        default_factory=list,
        description="Advanced points that demonstrate expertise",
    )

    common_mistakes: List[str] = Field(
        default_factory=list,
        description="Common mistakes or misconceptions to watch for",
    )

    difficulty_assessment: str = Field(
        ...,
        description="Assessment of question difficulty: 'basic', 'intermediate', 'advanced', 'expert'",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "reference_answer": "A process is an independent execution unit with its own memory space, while a thread is a lightweight unit within a process sharing the same memory. Processes are isolated and communicate via IPC (pipes, sockets), while threads share memory but need synchronization (mutexes, semaphores). Choose processes for isolation and fault tolerance, threads for shared state and lower overhead.",
                "key_points": [
                    "Memory isolation difference",
                    "Communication mechanisms",
                    "When to choose each",
                ],
                "advanced_points": [
                    "Context switching costs",
                    "Green threads vs OS threads",
                    "Process vs thread pools",
                ],
                "common_mistakes": [
                    "Confusing threads with coroutines",
                    "Ignoring synchronization needs",
                ],
                "difficulty_assessment": "intermediate",
            }
        }


class RubricScoreItem(BaseModel):
    """Individual rubric dimension score."""

    dimension: str = Field(
        ...,
        description="Scoring dimension name",
    )

    score: int = Field(
        ...,
        description="Score from 1-5",
        ge=1,
        le=5,
    )

    justification: str = Field(
        ...,
        description="Brief justification for this score",
        max_length=200,
    )


class RubricScoringOutput(BaseModel):
    """
    Structured output for rubric-based scoring.

    Scores each Q&A pair against the reference answer
    on standardized dimensions.
    """

    # Core dimensions (1-5 scale)
    correctness: RubricScoreItem = Field(
        ...,
        description="Factual accuracy compared to reference",
    )

    depth: RubricScoreItem = Field(
        ...,
        description="Technical depth and completeness",
    )

    reasoning: RubricScoreItem = Field(
        ...,
        description="Quality of logical explanation",
    )

    clarity: RubricScoreItem = Field(
        ...,
        description="Communication and structure",
    )

    # Computed scores
    overall_score: float = Field(
        ...,
        description="Weighted average of all dimensions (1-5)",
        ge=1,
        le=5,
    )

    normalized_score: float = Field(
        ...,
        description="Score normalized to 0-100 scale",
        ge=0,
        le=100,
    )

    # Qualitative assessment
    strength_areas: List[str] = Field(
        default_factory=list,
        description="Areas where the candidate excelled",
    )

    improvement_areas: List[str] = Field(
        default_factory=list,
        description="Areas needing improvement",
    )

    # Comparison to reference
    coverage_percentage: float = Field(
        ...,
        description="Percentage of key points covered",
        ge=0,
        le=100,
    )

    advanced_points_hit: int = Field(
        default=0,
        description="Number of advanced points covered",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "correctness": {
                    "dimension": "correctness",
                    "score": 4,
                    "justification": "Accurately explained core differences with minor omission of IPC details",
                },
                "depth": {
                    "dimension": "depth",
                    "score": 3,
                    "justification": "Covered basics well but didn't explore advanced scenarios",
                },
                "reasoning": {
                    "dimension": "reasoning",
                    "score": 4,
                    "justification": "Good logical flow connecting concepts to use cases",
                },
                "clarity": {
                    "dimension": "clarity",
                    "score": 4,
                    "justification": "Clear explanation with good structure",
                },
                "overall_score": 3.75,
                "normalized_score": 68.75,
                "strength_areas": ["Conceptual understanding", "Practical examples"],
                "improvement_areas": ["Advanced synchronization", "Performance considerations"],
                "coverage_percentage": 75.0,
                "advanced_points_hit": 1,
            }
        }


class PillarEvaluationSummary(BaseModel):
    """Summary evaluation for a single pillar/topic."""

    pillar_name: str = Field(..., description="Name of the pillar/topic")
    questions_count: int = Field(..., description="Number of questions asked")
    average_score: float = Field(..., ge=0, le=100)
    strongest_area: Optional[str] = Field(default=None)
    weakest_area: Optional[str] = Field(default=None)
    key_observations: List[str] = Field(default_factory=list)


class EvaluationAggregateOutput(BaseModel):
    """
    Structured output for aggregate evaluation metrics.

    Combines individual question scores into pillar-level
    and interview-level metrics.
    """

    # Interview-level metrics
    total_questions: int = Field(..., description="Total questions asked")
    total_follow_ups: int = Field(..., description="Total follow-up questions")

    # Overall scores
    overall_score: float = Field(
        ...,
        description="Weighted overall score (0-100)",
        ge=0,
        le=100,
    )

    confidence_interval: tuple[float, float] = Field(
        default=(0.0, 100.0),
        description="95% confidence interval for overall score",
    )

    # Per-pillar breakdown
    pillar_summaries: List[PillarEvaluationSummary] = Field(
        ...,
        description="Evaluation summary for each pillar",
    )

    # Dimension averages
    average_correctness: float = Field(..., ge=0, le=100)
    average_depth: float = Field(..., ge=0, le=100)
    average_reasoning: float = Field(..., ge=0, le=100)
    average_clarity: float = Field(..., ge=0, le=100)

    # Performance patterns
    strongest_pillars: List[str] = Field(default_factory=list)
    weakest_pillars: List[str] = Field(default_factory=list)
    improvement_trajectory: str = Field(
        default="stable",
        description="Performance trend: 'improving', 'declining', 'stable', 'inconsistent'",
    )

    # Cheating impact
    cheating_deductions: float = Field(
        default=0.0,
        description="Points deducted due to cheating flags",
    )

    adjusted_score: float = Field(
        ...,
        description="Final score after cheating deductions",
        ge=0,
        le=100,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_questions": 15,
                "total_follow_ups": 5,
                "overall_score": 72.5,
                "confidence_interval": (68.0, 77.0),
                "pillar_summaries": [
                    {
                        "pillar_name": "Data Structures",
                        "questions_count": 5,
                        "average_score": 78.0,
                        "strongest_area": "Array operations",
                        "weakest_area": "Tree balancing",
                        "key_observations": ["Strong fundamentals", "Needs work on advanced trees"],
                    }
                ],
                "average_correctness": 75.0,
                "average_depth": 68.0,
                "average_reasoning": 72.0,
                "average_clarity": 80.0,
                "strongest_pillars": ["Data Structures", "System Design"],
                "weakest_pillars": ["Concurrency"],
                "improvement_trajectory": "stable",
                "cheating_deductions": 0.0,
                "adjusted_score": 72.5,
            }
        }
