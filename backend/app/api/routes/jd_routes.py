"""API routes for Job Description management."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import JobDescription
from app.schemas.schemas import JDCreateRequest, JDResponse, JDObject
from app.services.graphs.jd_intelligence import build_jd_intelligence_graph
from app.services.vector_store.chroma_service import get_chroma_service
from app.api.middleware.auth_middleware import require_recruiter, AuthenticatedUser
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/jd", tags=["Job Descriptions"])


@router.post("/", response_model=JDResponse)
async def create_jd(
    request: JDCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Create and parse a new job description using JD Intelligence Graph."""
    # Run JD Intelligence Graph
    graph = build_jd_intelligence_graph()
    result = await graph.ainvoke({
        "raw_text": request.raw_text,
        "title": request.title,
        "parsed_role": "",
        "must_have_skills": [],
        "good_to_have": [],
        "experience_range": "",
        "tools": [],
        "competencies": [],
        "jd_object": {},
    })

    jd_obj = result.get("jd_object", {})

    # Store in database
    jd = JobDescription(
        title=request.title,
        raw_text=request.raw_text,
        parsed_data=jd_obj,
        must_have_skills=jd_obj.get("must_have_skills", []),
        good_to_have_skills=jd_obj.get("good_to_have", []),
        experience_range=jd_obj.get("experience_range", ""),
        tools=jd_obj.get("tools", []),
        competencies=jd_obj.get("competencies", []),
    )
    db.add(jd)
    await db.flush()

    # Embed in ChromaDB
    chroma = get_chroma_service()
    chunks = [request.raw_text]
    chroma.add_jd_chunks(
        jd_id=str(jd.jd_id),
        chunks=chunks,
        metadata_list=[{"title": request.title}],
    )
    jd.chroma_collection_id = str(jd.jd_id)

    logger.info(f"JD created by {user.email}: {jd.jd_id}")
    return jd


@router.get("/", response_model=List[JDResponse])
async def list_jds(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """List all job descriptions."""
    result = await db.execute(
        select(JobDescription).order_by(JobDescription.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{jd_id}", response_model=JDResponse)
async def get_jd(
    jd_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get a specific job description."""
    jd = await db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    return jd

@router.delete("/{jd_id}", status_code=204)
async def delete_jd(
    jd_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Delete a job description and all associated candidates."""
    jd = await db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    await db.delete(jd)
    logger.info(f"JD {jd_id} deleted by {user.email}")
    return None
