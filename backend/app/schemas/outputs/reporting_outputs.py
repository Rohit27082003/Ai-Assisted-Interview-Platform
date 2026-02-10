from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class StrengthWeakness(BaseModel):
    """Details for a strength or weakness."""
    area: str
    observation: str
    evidence: List[str]
    impact: str = Field(description="high, medium, or low")

class PerformanceAnalysisOutput(BaseModel):
    """Output for performance analysis."""
    strengths: List[StrengthWeakness]
    weaknesses: List[StrengthWeakness]
    performance_summary: str
    skill_profile: Dict[str, float]
    standout_answers: List[str]
    concerning_answers: List[str]
    communication_quality: str
    problem_solving_approach: str
    integrity_concerns: bool
    integrity_notes: Optional[str] = None

class HiringRecommendationOutput(BaseModel):
    """Output for hiring recommendation."""
    recommendation: str = Field(description="strong_hire, hire, borderline, no_hire, or strong_no_hire")
    confidence: float = Field(ge=0.0, le=1.0)
    primary_reasons: List[str]
    concerns: List[str]
    role_fit_score: float = Field(ge=0.0, le=100.0)
    role_fit_rationale: str
    growth_potential: str
    suggested_level: Optional[str] = None
    conditional_factors: List[str]
    summary: Optional[str] = Field(description="Summary of the recommendation", default="")
