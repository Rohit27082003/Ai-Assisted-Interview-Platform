from typing import List, Optional
from pydantic import BaseModel, Field

# ── Resume Parsing Models ──────────────────────────────────────────────────

class Project(BaseModel):
    name: str = Field(description="Name of the project")
    description: str = Field(description="Brief description of the project")
    tech_stack: List[str] = Field(description="List of technologies used in the project", default_factory=list)

class ResumeData(BaseModel):
    skills: List[str] = Field(description="List of technical skills, languages, and frameworks", default_factory=list)
    projects: List[Project] = Field(description="List of key projects", default_factory=list)
    experience_years: float = Field(description="Total years of full-time professional experience", default=0.0)
    companies: List[str] = Field(description="List of companies worked for", default_factory=list)
    education: str = Field(description="Highest degree obtained", default="Unknown")
    certifications: List[str] = Field(description="List of certifications", default_factory=list)
    key_claims: List[str] = Field(description="Specific measurable claims made in the resume", default_factory=list)
    summary: str = Field(description="Professional summary of the candidate", default="")

# ── Semantic Matching Models ───────────────────────────────────────────────

class ScoringDetails(BaseModel):
    skills_score: float = Field(description="Score (0-100) for skills match", ge=0, le=100)
    projects_score: float = Field(description="Score (0-100) for project relevance", ge=0, le=100)
    experience_score: float = Field(description="Score (0-100) for experience fit", ge=0, le=100)
    tooling_score: float = Field(description="Score (0-100) for tooling match", ge=0, le=100)
    overall_match_confidence: float = Field(description="Overall confidence score (0-100)", ge=0, le=100)
    reasoning: str = Field(description="Detailed explanation of the score, mentioning specific gaps")
    pros: List[str] = Field(description="List of strong points", default_factory=list)
    cons: List[str] = Field(description="List of weaknesses or gaps", default_factory=list)
    missing_critical_skills: List[str] = Field(description="List of required skills missing from the resume", default_factory=list)
    red_flags: List[str] = Field(description="Potential red flags (exaggeration, job hopping, etc.)", default_factory=list)
