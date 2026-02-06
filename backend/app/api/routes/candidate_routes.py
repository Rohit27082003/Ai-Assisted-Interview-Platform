"""API routes for Candidate management, resume upload, and shortlisting."""

from uuid import UUID
from typing import List
from pathlib import Path
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import Candidate, JobDescription, CandidateStatus
from app.schemas.schemas import (
    CandidateCreateRequest,
    CandidateResponse,
    ShortlistResponse,
    ShortlistResult,
    FocusArea,
    FocusAreaResponse,
    CandidateSessionInfo,
    GenerateSessionsResponse,
)
from app.services.graphs.resume_intelligence import build_resume_intelligence_graph
from app.services.graphs.focus_area import build_focus_area_graph
from app.services.aws.s3_service import get_s3_service
from app.api.middleware.auth_middleware import (
    require_recruiter,
    AuthenticatedUser,
    generate_session_id,
)
from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/candidates", tags=["Candidates"])

# Local uploads directory for development fallback
UPLOADS_DIR = Path(__file__).parent.parent.parent.parent / "uploads" / "resumes"


@router.post("/", response_model=CandidateResponse)
async def create_candidate(
    request: CandidateCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
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
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Upload and parse a candidate's resume."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Read file content
    content = await file.read()

    # Upload to S3 (with local fallback)
    resume_url = None
    try:
        s3 = get_s3_service()
        resume_url = await s3.upload_resume(content, file.filename, str(candidate_id))
        candidate.resume_s3_url = resume_url
    except Exception as e:
        logger.warning(f"S3 upload failed, using local storage: {e}")
        # Fallback to local storage
        try:
            UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "pdf"
            local_path = UPLOADS_DIR / f"{candidate_id}.{ext}"
            local_path.write_bytes(content)
            resume_url = f"local://{local_path}"
            candidate.resume_s3_url = resume_url
            logger.info(f"Resume saved locally: {local_path}")
        except Exception as local_err:
            logger.error(f"Local storage also failed: {local_err}")

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


@router.get("/{candidate_id}/resume")
async def get_resume_url(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get resume - returns presigned S3 URL or serves local file."""
    from fastapi.responses import FileResponse
    
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    if not candidate.resume_s3_url:
        raise HTTPException(status_code=404, detail="Resume not uploaded")
    
    resume_url = candidate.resume_s3_url
    
    # Handle local files
    if resume_url.startswith("local://"):
        local_path = Path(resume_url.replace("local://", ""))
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="Resume file not found")
        return FileResponse(
            path=local_path,
            media_type="application/pdf",
            filename=f"{candidate.name}_resume.pdf"
        )
    
    # Handle S3 files
    try:
        s3 = get_s3_service()
        presigned_url = s3.generate_presigned_url(resume_url)
        logger.info(f"Generated presigned URL for candidate {candidate_id} resume")
        return {"download_url": presigned_url}
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download URL")

@router.post("/{jd_id}/shortlist", response_model=ShortlistResponse)
async def shortlist_candidates(
    jd_id: UUID,
    threshold: float = Query(default=0.65, ge=0.0, le=1.0, description="Score threshold for shortlisting"),
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """
    Run shortlisting for all parsed candidates under a JD.
    
    The threshold parameter controls the minimum score required for shortlisting.
    """
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
        # Use threshold parameter instead of hardcoded value
        recommended = score >= threshold

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
        f"Shortlisting complete for JD {jd_id} (threshold={threshold}): "
        f"{len(shortlisted)} shortlisted, {len(rejected)} rejected"
    )

    return ShortlistResponse(
        jd_id=jd_id,
        total_candidates=len(shortlisted) + len(rejected),
        threshold_used=threshold,
        shortlisted=shortlisted,
        rejected=rejected,
    )


@router.post("/{candidate_id}/focus-areas", response_model=FocusAreaResponse)
async def generate_focus_areas(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
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


@router.post("/{jd_id}/rerun-shortlist", response_model=ShortlistResponse)
async def rerun_shortlist(
    jd_id: UUID,
    threshold: float = Query(..., ge=0.0, le=1.0, description="New threshold for shortlisting"),
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """
    Re-run shortlisting with a new threshold.
    
    This endpoint resets previously shortlisted/rejected candidates back to PARSED status,
    then re-evaluates them using the new threshold.
    """
    # Get JD
    jd = await db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Reset shortlisted/rejected candidates to PARSED (but don't touch candidates in interview)
    result = await db.execute(
        select(Candidate).where(
            Candidate.jd_id == jd_id,
            Candidate.status.in_([CandidateStatus.SHORTLISTED, CandidateStatus.REJECTED]),
        )
    )
    candidates = result.scalars().all()

    if not candidates:
        raise HTTPException(
            status_code=404, 
            detail="No shortlisted or rejected candidates found to re-evaluate"
        )

    shortlisted = []
    rejected = []

    for candidate in candidates:
        # Use existing score if available (skip re-running the graph)
        score = candidate.shortlist_score or 0.0
        
        # Apply new threshold
        recommended = score >= threshold

        # Update status based on new threshold
        candidate.status = (
            CandidateStatus.SHORTLISTED if recommended
            else CandidateStatus.REJECTED
        )
        # Clear session if moving back to rejected
        if not recommended:
            candidate.session_id = None
            candidate.session_expires_at = None

        result_item = ShortlistResult(
            candidate_id=candidate.candidate_id,
            name=candidate.name,
            email=candidate.email,
            shortlist_score=score,
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
        f"Re-shortlisting complete for JD {jd_id} (threshold={threshold}): "
        f"{len(shortlisted)} shortlisted, {len(rejected)} rejected"
    )

    return ShortlistResponse(
        jd_id=jd_id,
        total_candidates=len(shortlisted) + len(rejected),
        threshold_used=threshold,
        shortlisted=shortlisted,
        rejected=rejected,
    )


@router.post("/{jd_id}/generate-sessions", response_model=GenerateSessionsResponse)
async def generate_candidate_sessions(
    jd_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """
    Generate session IDs for all shortlisted candidates under a JD.
    
    These session IDs allow candidates to log in to the interview portal
    using their session ID and email address.
    """
    # Get JD
    jd = await db.get(JobDescription, jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Get shortlisted candidates without existing sessions
    # STRICT: Only generate sessions for candidates who have Focus Areas generated (FOCUS_READY)
    result = await db.execute(
        select(Candidate).where(
            Candidate.jd_id == jd_id,
            Candidate.status == CandidateStatus.FOCUS_READY,
        )
    )
    candidates = result.scalars().all()

    if not candidates:
        raise HTTPException(
            status_code=404, 
            detail="No candidates with generated Focus Areas found. Please generate focus areas first."
        )

    sessions = []
    session_expiry = datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_EXPIRY_HOURS)

    for candidate in candidates:
        # Generate new session ID (or keep existing if valid)
        if not candidate.session_id or (
            candidate.session_expires_at and 
            candidate.session_expires_at < datetime.now(timezone.utc)
        ):
            candidate.session_id = generate_session_id(settings.SESSION_ID_LENGTH)
            candidate.session_expires_at = session_expiry
            candidate.session_created_at = datetime.now(timezone.utc)

        sessions.append(CandidateSessionInfo(
            candidate_id=candidate.candidate_id,
            name=candidate.name,
            email=candidate.email,
            session_id=candidate.session_id,
            session_expires_at=candidate.session_expires_at,
        ))

    logger.info(f"Generated sessions for {len(sessions)} candidates under JD {jd_id}")

    return GenerateSessionsResponse(
        jd_id=jd_id,
        total_generated=len(sessions),
        sessions=sessions,
    )


@router.get("/", response_model=List[CandidateResponse])
async def list_candidates(
    jd_id: UUID = None,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """List candidates, optionally filtered by JD."""
    query = select(Candidate).options(selectinload(Candidate.interviews)).order_by(Candidate.created_at.desc())
    if jd_id:
        query = query.where(Candidate.jd_id == jd_id)
    result = await db.execute(query)
    candidates = result.scalars().all()
    
    # Attach latest interview_id if exists
    for c in candidates:
        if c.interviews:
            #Sort by created_at desc to get latest
            latest = sorted(c.interviews, key=lambda i: i.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[0]
            c.interview_id = latest.interview_id
            
    return candidates


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get a specific candidate."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Delete a candidate."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    await db.delete(candidate)
    await db.commit()
