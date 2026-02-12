"""Pydantic schemas for API request models."""

from __future__ import annotations
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ── JD Requests ──────────────────────────────────────────────────

class JDCreateRequest(BaseModel):
    title: str
    raw_text: str


# ── Candidate Requests ───────────────────────────────────────────

class CandidateCreateRequest(BaseModel):
    name: str
    email: str
    jd_id: UUID


class ShortlistRequest(BaseModel):
    """Request for shortlisting with custom threshold."""
    threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class CreateSessionRequest(BaseModel):
    """Request to create a candidate session with optional time window."""
    interview_window_start: Optional[datetime] = None
    interview_window_end: Optional[datetime] = None
    send_email: bool = True


class UpdateTimeWindowRequest(BaseModel):
    """Request to update a candidate's interview time window."""
    interview_window_start: Optional[datetime] = None
    interview_window_end: Optional[datetime] = None
    send_notification: bool = Field(default=True, description="Send email notification to candidate about time window change")


# ── Interview Requests ───────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    candidate_id: UUID


class InterviewAnswerSubmit(BaseModel):
    interview_id: UUID
    transcript_id: UUID
    answer_text: str
