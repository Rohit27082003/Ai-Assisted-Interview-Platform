from pydantic import BaseModel, Field
from typing import List, Optional

class ReferenceAnswerOutput(BaseModel):
    """Output for reference answer generation."""
    reference_answer: str = Field(description="The complete reference answer a strong candidate would give")
    key_points: List[str] = Field(description="List of essential points that MUST be covered")
    advanced_points: List[str] = Field(description="List of advanced points showing expertise")
    common_mistakes: List[str] = Field(description="List of common mistakes to watch for")
    difficulty_assessment: str = Field(description="Assessment of difficulty: basic, intermediate, advanced, or expert")

class RubricDimension(BaseModel):
    """Score for a specific dimension."""
    dimension: str
    score: int = Field(ge=1, le=5)
    justification: str

class RubricScoreOutput(BaseModel):
    """Output for rubric scoring."""
    correctness: RubricDimension
    depth: RubricDimension
    reasoning: RubricDimension
    clarity: RubricDimension
    relevance: RubricDimension = Field(description="How relevant the answer is to the question")
    practical_application: RubricDimension = Field(description="Evidence of practical experience and application")

    overall_score: float = Field(ge=1.0, le=5.0)
    normalized_score: float = Field(ge=0.0, le=100.0)

    expected_vs_actual_comparison: str = Field(description="Detailed comparison between expected reference answer and actual candidate answer")
    similarity_score: float = Field(ge=0.0, le=1.0, description="Semantic similarity score between 0.0 and 1.0")

    strength_areas: List[str] = Field(default_factory=list)
    improvement_areas: List[str] = Field(default_factory=list)
    coverage_percentage: float = Field(default=0.0)
    advanced_points_hit: int = Field(default=0)
