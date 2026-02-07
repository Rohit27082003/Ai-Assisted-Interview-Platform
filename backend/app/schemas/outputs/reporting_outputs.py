"""
Structured Output Schemas for Final Reporting

These schemas define the expected LLM output format for:
- Performance analysis
- Hiring recommendations
- Final comprehensive reports
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StrengthWeaknessItem(BaseModel):
    """A single strength or weakness observation."""

    area: str = Field(..., description="The skill or competency area")
    observation: str = Field(..., description="Specific observation")
    evidence: List[str] = Field(
        default_factory=list,
        description="Supporting evidence from interview",
    )
    impact: str = Field(
        default="medium",
        description="Impact level: 'high', 'medium', 'low'",
    )


class PerformanceAnalysisOutput(BaseModel):
    """
    Structured output for performance analysis.

    Analyzes all evaluations to identify patterns,
    strengths, weaknesses, and overall performance profile.
    """

    # Strengths and weaknesses
    strengths: List[StrengthWeaknessItem] = Field(
        ...,
        description="Top 3-5 identified strengths",
        min_length=1,
        max_length=5,
    )

    weaknesses: List[StrengthWeaknessItem] = Field(
        ...,
        description="Top 3-5 identified weaknesses",
        min_length=1,
        max_length=5,
    )

    # Performance summary
    performance_summary: str = Field(
        ...,
        description="2-3 sentence summary of overall performance",
        min_length=50,
        max_length=500,
    )

    # Skill profile
    skill_profile: Dict[str, float] = Field(
        ...,
        description="Skill area to score mapping (0-100)",
    )

    # Notable moments
    standout_answers: List[str] = Field(
        default_factory=list,
        description="Questions where candidate excelled",
    )

    concerning_answers: List[str] = Field(
        default_factory=list,
        description="Questions revealing significant gaps",
    )

    # Behavioral indicators
    communication_quality: str = Field(
        ...,
        description="Assessment of communication: 'excellent', 'good', 'adequate', 'needs_improvement'",
    )

    problem_solving_approach: str = Field(
        ...,
        description="How candidate approaches problems: 'systematic', 'intuitive', 'scattered', 'methodical'",
    )

    # Cheating assessment
    integrity_concerns: bool = Field(
        default=False,
        description="Whether there are integrity concerns",
    )

    integrity_notes: Optional[str] = Field(
        default=None,
        description="Notes on any integrity concerns",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "strengths": [
                    {
                        "area": "Data Structures",
                        "observation": "Strong understanding of core data structures and their trade-offs",
                        "evidence": ["Correctly analyzed time complexity", "Good explanation of hash table internals"],
                        "impact": "high",
                    }
                ],
                "weaknesses": [
                    {
                        "area": "Concurrency",
                        "observation": "Limited experience with thread synchronization",
                        "evidence": ["Struggled with deadlock prevention question"],
                        "impact": "medium",
                    }
                ],
                "performance_summary": "Candidate demonstrates solid foundational knowledge in data structures and algorithms with good communication skills. Areas for growth include concurrency patterns and system design at scale.",
                "skill_profile": {
                    "Data Structures": 82.0,
                    "Algorithms": 75.0,
                    "System Design": 68.0,
                    "Concurrency": 55.0,
                },
                "standout_answers": ["Q3: Excellent hash table analysis"],
                "concerning_answers": ["Q8: Incomplete deadlock explanation"],
                "communication_quality": "good",
                "problem_solving_approach": "methodical",
                "integrity_concerns": False,
                "integrity_notes": None,
            }
        }


class RecommendationOutput(BaseModel):
    """
    Structured output for hiring recommendation.

    Provides a clear hiring decision with supporting rationale.
    """

    # Primary recommendation
    recommendation: str = Field(
        ...,
        description="Hiring recommendation: 'strong_hire', 'hire', 'borderline', 'no_hire', 'strong_no_hire'",
    )

    confidence: float = Field(
        ...,
        description="Confidence in recommendation (0-1)",
        ge=0,
        le=1,
    )

    # Rationale
    primary_reasons: List[str] = Field(
        ...,
        description="Top 3 reasons supporting this recommendation",
        min_length=1,
        max_length=5,
    )

    concerns: List[str] = Field(
        default_factory=list,
        description="Any concerns even for positive recommendations",
    )

    # Role fit
    role_fit_score: float = Field(
        ...,
        description="How well candidate fits the specific role (0-100)",
        ge=0,
        le=100,
    )

    role_fit_rationale: str = Field(
        ...,
        description="Explanation of role fit assessment",
    )

    # Growth potential
    growth_potential: str = Field(
        ...,
        description="Assessment of growth potential: 'high', 'moderate', 'limited'",
    )

    # Suggested level
    suggested_level: Optional[str] = Field(
        default=None,
        description="Suggested seniority level if hire: 'junior', 'mid', 'senior', 'staff'",
    )

    # Conditions
    conditional_factors: List[str] = Field(
        default_factory=list,
        description="Conditions that might change recommendation",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "recommendation": "hire",
                "confidence": 0.78,
                "primary_reasons": [
                    "Strong foundational knowledge in core areas",
                    "Good problem-solving approach",
                    "Clear communication skills",
                ],
                "concerns": [
                    "Limited experience with distributed systems",
                    "Would benefit from mentorship on concurrency",
                ],
                "role_fit_score": 75.0,
                "role_fit_rationale": "Candidate meets most requirements for the backend engineer role. Gaps in distributed systems are addressable with onboarding.",
                "growth_potential": "high",
                "suggested_level": "mid",
                "conditional_factors": [
                    "Team's ability to provide mentorship",
                    "Project complexity requirements",
                ],
            }
        }


class FinalReportOutput(BaseModel):
    """
    Comprehensive final report combining all analysis.

    This is the complete structured output for the final
    interview report shown to recruiters.
    """

    # Header info
    candidate_name: str
    job_title: str
    interview_date: str
    interview_duration_minutes: int

    # Scores
    final_score: float = Field(..., ge=0, le=100)
    adjusted_score: float = Field(..., ge=0, le=100)  # After any deductions

    # Recommendation
    recommendation: str  # 'strong_hire', 'hire', 'borderline', 'no_hire', 'strong_no_hire'
    recommendation_confidence: float = Field(..., ge=0, le=1)

    # Performance breakdown
    pillar_scores: Dict[str, float] = Field(
        ...,
        description="Score per interview pillar/topic",
    )

    dimension_scores: Dict[str, float] = Field(
        ...,
        description="Average scores per rubric dimension",
    )

    # Qualitative analysis
    strengths: List[Dict[str, str]] = Field(
        ...,
        description="List of strength observations",
    )

    weaknesses: List[Dict[str, str]] = Field(
        ...,
        description="List of weakness observations",
    )

    # Summary
    executive_summary: str = Field(
        ...,
        description="2-3 paragraph executive summary for hiring manager",
        min_length=200,
        max_length=1500,
    )

    # Detailed feedback
    detailed_feedback: Dict[str, str] = Field(
        ...,
        description="Detailed feedback per pillar",
    )

    # Cheating/integrity
    cheating_flags: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Any cheating flags raised during interview",
    )

    integrity_assessment: str = Field(
        default="clean",
        description="Overall integrity: 'clean', 'minor_concerns', 'major_concerns', 'disqualified'",
    )

    # Interview metadata
    questions_asked: int
    follow_ups_asked: int
    pillars_covered: int
    completion_status: str  # 'completed', 'terminated', 'timeout'

    # Next steps
    suggested_next_steps: List[str] = Field(
        default_factory=list,
        description="Suggested next steps for this candidate",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "candidate_name": "John Doe",
                "job_title": "Senior Backend Engineer",
                "interview_date": "2024-01-15",
                "interview_duration_minutes": 45,
                "final_score": 72.5,
                "adjusted_score": 72.5,
                "recommendation": "hire",
                "recommendation_confidence": 0.78,
                "pillar_scores": {
                    "Data Structures": 82.0,
                    "System Design": 68.0,
                    "Concurrency": 55.0,
                },
                "dimension_scores": {
                    "correctness": 75.0,
                    "depth": 68.0,
                    "reasoning": 72.0,
                    "clarity": 80.0,
                },
                "strengths": [
                    {"area": "Data Structures", "observation": "Strong fundamentals"},
                ],
                "weaknesses": [
                    {"area": "Concurrency", "observation": "Needs more experience"},
                ],
                "executive_summary": "John demonstrated solid technical foundations...",
                "detailed_feedback": {
                    "Data Structures": "Excellent understanding of core concepts...",
                },
                "cheating_flags": [],
                "integrity_assessment": "clean",
                "questions_asked": 15,
                "follow_ups_asked": 5,
                "pillars_covered": 4,
                "completion_status": "completed",
                "suggested_next_steps": [
                    "Proceed to system design round",
                    "Team fit interview",
                ],
            }
        }
