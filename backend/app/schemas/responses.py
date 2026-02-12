"""Pydantic schemas for API response models."""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ── Shared Models ────────────────────────────────────────────────

class FocusArea(BaseModel):
    skill: str
    reason: str


class JDObject(BaseModel):
    """Typed output from JD Intelligence Graph."""
    role: str = ""
    must_have_skills: List[str] = Field(default_factory=list)
    good_to_have: List[str] = Field(default_factory=list)
    experience_range: str = ""
    tools: List[str] = Field(default_factory=list)
    competencies: List[str] = Field(default_factory=list)


# ── JD Responses ─────────────────────────────────────────────────

class JDResponse(BaseModel):
    jd_id: UUID
    title: str
    parsed_data: Optional[JDObject] = None
    must_have_skills: List[str] = Field(default_factory=list)
    good_to_have_skills: List[str] = Field(default_factory=list)
    experience_range: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    competencies: List[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


# ── Candidate Responses ──────────────────────────────────────────

class CandidateResponse(BaseModel):
    candidate_id: UUID
    jd_id: UUID
    name: str
    email: str
    resume_s3_url: Optional[str] = None
    shortlist_score: float = 0.0
    status: str
    focus_areas: List[FocusArea] = Field(default_factory=list)
    interview_id: Optional[UUID] = None
    scoring_analysis: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ShortlistResult(BaseModel):
    candidate_id: UUID
    name: str
    email: str
    shortlist_score: float
    skills_match: float = 0.0
    projects_match: float = 0.0
    experience_match: float = 0.0
    tooling_match: float = 0.0
    recommended: bool = False
    reasoning: Optional[str] = None


class ShortlistResponse(BaseModel):
    jd_id: UUID
    total_candidates: int
    threshold_used: float = 0.65
    shortlisted: List[ShortlistResult]
    rejected: List[ShortlistResult]


class CandidateSessionInfo(BaseModel):
    """Session info for a single candidate."""
    candidate_id: UUID
    name: str
    email: str
    session_id: str
    session_expires_at: datetime
    interview_window_start: Optional[datetime] = None
    interview_window_end: Optional[datetime] = None


class EmailSendResult(BaseModel):
    """Result of sending an email to a candidate."""
    email: str
    status: str  # "sent" | "failed"
    error: Optional[str] = None


class GenerateSessionsResponse(BaseModel):
    """Response when generating sessions for shortlisted candidates."""
    jd_id: UUID
    total_generated: int
    sessions: List[CandidateSessionInfo]
    emails_sent: Optional[List[EmailSendResult]] = None


class FocusAreaResponse(BaseModel):
    candidate_id: UUID
    focus_areas: List[FocusArea]


# ── Interview Responses ──────────────────────────────────────────

class InterviewQuestion(BaseModel):
    question_number: int
    pillar: str
    question_text: str
    is_follow_up: bool = False
    reading_time_seconds: int = 20
    answer_time_seconds: int = 45


class InterviewProgress(BaseModel):
    interview_id: UUID
    candidate_id: UUID
    status: str
    current_pillar: str
    question_number: int
    total_questions: int
    cheating_level: str


class InterviewResponse(BaseModel):
    interview_id: UUID
    candidate_id: UUID
    status: str
    started_at: Optional[datetime] = None
    current_pillar: Optional[str] = None
    question_number: int = 0
    transcript: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ── Evaluation Responses ─────────────────────────────────────────

class EvaluationItem(BaseModel):
    question: str
    answer: str
    reference_answer: str
    correctness: int = Field(ge=1, le=5)
    depth: int = Field(ge=1, le=5)
    reasoning: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    overall_score: float
    justification: str


class EvaluationResponse(BaseModel):
    interview_id: UUID
    evaluations: List[EvaluationItem]
    average_score: float


# ── Report Responses ─────────────────────────────────────────────

class AnswerAnalysis(BaseModel):
    """Real-time answer analysis signals from answer_analyzer node."""
    available: bool = Field(description="Whether analysis is available for this question")
    note: Optional[str] = Field(None, description="Note if analysis is not available")
    overall_signal_score: Optional[float] = Field(None, ge=0, le=10, description="Combined quality score 0-10")
    is_relevant: Optional[bool] = Field(None, description="Whether answer is on-topic")
    quality_scores: Optional[Dict[str, float]] = Field(None, description="Individual quality metrics")
    key_concepts_covered: List[str] = Field(default_factory=list, description="Concepts candidate mentioned")
    missing_concepts: List[str] = Field(default_factory=list, description="Concepts candidate missed")
    has_gaps: Optional[bool] = Field(None, description="Whether follow-up is needed")
    analysis_summary: Optional[str] = Field(None, description="AI-generated summary")

    class Config:
        json_schema_extra = {
            "example": {
                "available": True,
                "overall_signal_score": 7.8,
                "is_relevant": True,
                "quality_scores": {"correctness": 7.5, "depth": 8.0, "clarity": 8.0},
                "key_concepts_covered": ["Caching", "Load balancing"],
                "missing_concepts": ["CDN strategy"],
                "has_gaps": True,
                "analysis_summary": "Good understanding but missed some advanced topics"
            }
        }


class ReportResponse(BaseModel):
    report_id: UUID
    interview_id: UUID
    candidate_name: str
    jd_title: str
    strengths: List[str]
    weaknesses: List[str]
    cheating_flags: List[Any]
    topic_scores: Dict[str, float]
    final_score: float
    confidence_score: float
    recommendation: str
    summary: str
    detailed_feedback: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
