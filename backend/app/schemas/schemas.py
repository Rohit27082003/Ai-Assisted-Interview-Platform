"""Pydantic schemas for API request/response and graph typed objects."""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ── JD Schemas ────────────────────────────────────────────────────

class JDCreateRequest(BaseModel):
    title: str
    raw_text: str


class JDObject(BaseModel):
    """Typed output from JD Intelligence Graph."""
    role: str = ""
    must_have_skills: List[str] = Field(default_factory=list)
    good_to_have: List[str] = Field(default_factory=list)
    experience_range: str = ""
    tools: List[str] = Field(default_factory=list)
    competencies: List[str] = Field(default_factory=list)


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


# ── Resume / Candidate Schemas ────────────────────────────────────

class CandidateCreateRequest(BaseModel):
    name: str
    email: str
    jd_id: UUID


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


class ShortlistResponse(BaseModel):
    jd_id: UUID
    total_candidates: int
    threshold_used: float = 0.65
    shortlisted: List[ShortlistResult]
    rejected: List[ShortlistResult]


# ── Session Schemas (for candidate login) ─────────────────────────

class ShortlistRequest(BaseModel):
    """Request for shortlisting with custom threshold."""
    threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class CandidateSessionInfo(BaseModel):
    """Session info for a single candidate."""
    candidate_id: UUID
    name: str
    email: str
    session_id: str
    session_expires_at: datetime


class GenerateSessionsResponse(BaseModel):
    """Response when generating sessions for shortlisted candidates."""
    jd_id: UUID
    total_generated: int
    sessions: List[CandidateSessionInfo]


# ── Focus Area Schemas ────────────────────────────────────────────

class FocusArea(BaseModel):
    skill: str
    reason: str


class FocusAreaResponse(BaseModel):
    candidate_id: UUID
    focus_areas: List[FocusArea]


# Update forward reference
CandidateResponse.model_rebuild()


# ── Interview Schemas ─────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    candidate_id: UUID


class InterviewQuestion(BaseModel):
    question_number: int
    pillar: str
    question_text: str
    is_follow_up: bool = False
    reading_time_seconds: int = 20
    answer_time_seconds: int = 45


class InterviewAnswerSubmit(BaseModel):
    interview_id: UUID
    transcript_id: UUID
    answer_text: str


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


# ── Evaluation Schemas ────────────────────────────────────────────

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


# ── Report Schemas ────────────────────────────────────────────────

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


# ── Graph State Schemas (Typed objects between graphs) ────────────

class CandidateGraphState(BaseModel):
    """Master state object persisted in Postgres JSONB."""
    candidate_id: str = ""
    jd_id: str = ""
    resume_vector_id: str = ""
    shortlist_score: float = 0.0
    focus_areas: List[FocusArea] = Field(default_factory=list)
    interview_progress: InterviewProgressState = None
    cheating_flags: List[Any] = Field(default_factory=list)
    evaluation: Dict[str, Any] = Field(default_factory=dict)
    report_id: str = ""
    status: str = "uploaded"


class InterviewProgressState(BaseModel):
    current_pillar: str = ""
    question_number: int = 0
    total_questions: int = 0
    pillars_completed: List[str] = Field(default_factory=list)


# Rebuild for forward refs
CandidateGraphState.model_rebuild()


# ── WebSocket Messages ────────────────────────────────────────────

class WSMessage(BaseModel):
    type: str  # question, timer, transcript, cheating_warning, complete, error
    data: Dict[str, Any]


class WSAudioChunk(BaseModel):
    interview_id: str
    chunk: str  # base64 encoded audio
    sequence: int

class WSViolationMessage(BaseModel):
    reason: str
