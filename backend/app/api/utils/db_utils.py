"""Database query helpers for route-level ownership verification."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Interview, Candidate, JobDescription, Report,
)


async def verify_interview_ownership(
    db: AsyncSession,
    interview_id: UUID,
    recruiter_id: UUID,
) -> Interview:
    """
    Verify a recruiter owns the interview via the
    Interview -> Candidate -> JobDescription -> Recruiter chain.

    Returns the Interview object if authorized.
    Raises HTTPException(404) if not found or unauthorized.
    """
    query = (
        select(Interview)
        .join(Candidate, Interview.candidate_id == Candidate.candidate_id)
        .join(JobDescription, Candidate.jd_id == JobDescription.jd_id)
        .where(
            Interview.interview_id == interview_id,
            JobDescription.recruiter_id == recruiter_id,
        )
    )
    result = await db.execute(query)
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


async def verify_report_ownership(
    db: AsyncSession,
    interview_id: UUID,
    recruiter_id: UUID,
) -> Report:
    """
    Verify a recruiter owns the report via the
    Report -> Interview -> Candidate -> JobDescription -> Recruiter chain.

    Returns the Report object if authorized.
    Raises HTTPException(404) if not found or unauthorized.
    """
    query = (
        select(Report)
        .join(Interview, Report.interview_id == Interview.interview_id)
        .join(Candidate, Interview.candidate_id == Candidate.candidate_id)
        .join(JobDescription, Candidate.jd_id == JobDescription.jd_id)
        .where(
            Report.interview_id == interview_id,
            JobDescription.recruiter_id == recruiter_id,
        )
    )
    result = await db.execute(query)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
