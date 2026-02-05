"""API routes for Candidate management, resume upload, and shortlisting."""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Candidate, JobDescription, CandidateStatus
from app.schemas.schemas import (
    CandidateCreateRequest,
    CandidateResponse,
    ShortlistResponse,
    ShortlistResult,
    FocusArea,
    FocusAreaResponse,
)
from app.services.graphs.resume_intelligence import build_resume_intelligence_graph
from app.services.graphs.focus_area import build_focus_area_graph
from app.services.aws.s3_service import get_s3_service
from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/candidates", tags=["Candidates"])


@router.post("/", response_model=CandidateResponse)
async def create_candidate(
    request: CandidateCreateRequest, db: AsyncSession = Depends(get_db)
):
    """Register a new candidate."""
    # Verify JD exists
    jd = await db.get(JobDescription, request.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    candidate = Candidate(
        name=request.name,
        email=request.email,
        jd_id=request.jd_id,
        status=CandidateStatus.UPLOADED,
    )
    db.add(candidate)
    await db.flush()
    logger.info(f"Candidate created: {candidate.candidate_id}")
    return candidate


@router.post("/{candidate_id}/upload-resume")
async def upload_resume(
    candidate_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload and parse a candidate's resume."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Read file content
    content = await file.read()

    # Upload to S3
    try:
        s3 = get_s3_service()
        s3_url = await s3.upload_resume(content, file.filename, str(candidate_id))
        candidate.resume_s3_url = s3_url
    except Exception as e:
        logger.warning(f"S3 upload failed (continuing without): {e}")

    # Extract text from resume
    resume_text = ""
    if file.filename.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(content))
            resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.error(f"PDF parsing failed: {e}")
            resume_text = content.decode("utf-8", errors="ignore")
    elif file.filename.endswith(".docx"):
        try:
            from docx import Document
            from io import BytesIO
            doc = Document(BytesIO(content))
            resume_text = "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.error(f"DOCX parsing failed: {e}")
            resume_text = content.decode("utf-8", errors="ignore")
    else:
        resume_text = content.decode("utf-8", errors="ignore")

    candidate.resume_text = resume_text
    candidate.status = CandidateStatus.PARSED

    logger.info(f"Resume uploaded for candidate {candidate_id}")
    return {"candidate_id": str(candidate_id), "status": "parsed", "text_length": len(resume_text)}


@router.post("/{jd_id}/shortlist", response_model=ShortlistResponse)
async def shortlist_candidates(
    jd_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run shortlisting for all parsed candidates under a JD."""
    # Get JD
    jd = await db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Get all parsed candidates
    result = await db.execute(
        select(Candidate).where(
            Candidate.jd_id == jd_id,
            Candidate.status == CandidateStatus.PARSED,
        )
    )
    candidates = result.scalars().all()

    if not candidates:
        raise HTTPException(status_code=404, detail="No parsed candidates found")

    shortlisted = []
    rejected = []

    for candidate in candidates:
        if not candidate.resume_text:
            continue

        # Run Resume Intelligence Graph
        graph = build_resume_intelligence_graph()
        graph_result = await graph.ainvoke({
            "candidate_id": str(candidate.candidate_id),
            "jd_id": str(jd_id),
            "resume_text": candidate.resume_text,
            "jd_object": jd.parsed_data or {},
            "chunks": [],
            "chunk_metadata": [],
            "skills_score": 0.0,
            "projects_score": 0.0,
            "experience_score": 0.0,
            "tooling_score": 0.0,
            "final_score": 0.0,
            "recommended": False,
            "scoring_details": {},
        })

        score = graph_result.get("final_score", 0.0)
        recommended = graph_result.get("recommended", False)

        # Update candidate
        candidate.shortlist_score = score
        candidate.status = (
            CandidateStatus.SHORTLISTED if recommended
            else CandidateStatus.REJECTED
        )

        result_item = ShortlistResult(
            candidate_id=candidate.candidate_id,
            name=candidate.name,
            email=candidate.email,
            shortlist_score=score,
            skills_match=graph_result.get("skills_score", 0),
            projects_match=graph_result.get("projects_score", 0),
            experience_match=graph_result.get("experience_score", 0),
            tooling_match=graph_result.get("tooling_score", 0),
            recommended=recommended,
        )

        if recommended:
            shortlisted.append(result_item)
        else:
            rejected.append(result_item)

    # Sort by score descending
    shortlisted.sort(key=lambda x: x.shortlist_score, reverse=True)
    rejected.sort(key=lambda x: x.shortlist_score, reverse=True)

    logger.info(
        f"Shortlisting complete for JD {jd_id}: "
        f"{len(shortlisted)} shortlisted, {len(rejected)} rejected"
    )

    return ShortlistResponse(
        jd_id=jd_id,
        total_candidates=len(shortlisted) + len(rejected),
        shortlisted=shortlisted,
        rejected=rejected,
    )


@router.post("/{candidate_id}/focus-areas", response_model=FocusAreaResponse)
async def generate_focus_areas(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Generate interview focus areas for a shortlisted candidate."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.status not in (CandidateStatus.SHORTLISTED, CandidateStatus.FOCUS_READY):
        raise HTTPException(status_code=400, detail="Candidate must be shortlisted first")

    jd = await db.get(JobDescription, candidate.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Run Focus Area Graph
    graph = build_focus_area_graph()
    result = await graph.ainvoke({
        "candidate_id": str(candidate_id),
        "jd_object": jd.parsed_data or {},
        "resume_text": candidate.resume_text or "",
        "resume_metadata": {},
        "focus_areas": [],
        "reasoning_trace": "",
    })

    focus_areas = result.get("focus_areas", [])

    # Persist focus areas
    candidate.focus_areas = focus_areas
    candidate.status = CandidateStatus.FOCUS_READY

    logger.info(f"Focus areas generated for candidate {candidate_id}: {len(focus_areas)}")
    return FocusAreaResponse(
        candidate_id=candidate_id,
        focus_areas=[FocusArea(**fa) for fa in focus_areas],
    )


@router.get("/", response_model=List[CandidateResponse])
async def list_candidates(
    jd_id: UUID = None, db: AsyncSession = Depends(get_db)
):
    """List candidates, optionally filtered by JD."""
    query = select(Candidate).order_by(Candidate.created_at.desc())
    if jd_id:
        query = query.where(Candidate.jd_id == jd_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific candidate."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate
