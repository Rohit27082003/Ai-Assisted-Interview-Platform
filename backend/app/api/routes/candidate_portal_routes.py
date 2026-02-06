"""Candidate Portal routes for session-based login and interview access."""

from uuid import UUID
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import Candidate, JobDescription, Interview, InterviewStatus, CandidateStatus
from app.api.middleware.auth_middleware import (
    require_candidate_session,
    AuthenticatedCandidate,
)
from app.services.aws.transcribe_service import get_transcribe_service
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/candidate-portal", tags=["Candidate Portal"])


# ── Schemas ──────────────────────────────────────────────────────


class PortalInfoResponse(BaseModel):
    """Response with candidate's portal information."""
    candidate_id: UUID
    name: str
    email: str
    job_title: str
    job_company: Optional[str] = None
    interview_status: Optional[str] = None
    interview_id: Optional[UUID] = None
    can_start_interview: bool
    instructions: str


class StartInterviewResponse(BaseModel):
    """Response when starting an interview."""
    interview_id: UUID
    candidate_id: UUID
    status: str
    message: str


# ── Portal Routes ────────────────────────────────────────────────


@router.get("/info", response_model=PortalInfoResponse)
async def get_portal_info(
    candidate: AuthenticatedCandidate = Depends(require_candidate_session),
    db: AsyncSession = Depends(get_db),
):
    """
    Get candidate's portal information.
    
    Requires X-Candidate-Session header with format: session_id:email
    """
    # Get job description
    jd = await db.get(JobDescription, candidate.jd_id)
    job_title = jd.title if jd else "Unknown Position"
    
    # Check for existing interview
    result = await db.execute(
        select(Interview).where(Interview.candidate_id == candidate.candidate_id)
    )
    interview = result.scalar_one_or_none()
    
    # Get current candidate status
    db_candidate = await db.get(Candidate, candidate.candidate_id)
    
    # Determine interview status and eligibility
    interview_status = None
    interview_id = None
    can_start = False
    
    if interview:
        interview_status = interview.status.value if interview.status else None
        interview_id = interview.interview_id
        can_start = interview.status == InterviewStatus.PENDING
    elif db_candidate:
        can_start = db_candidate.status in (
            CandidateStatus.SHORTLISTED,
            CandidateStatus.FOCUS_READY,
        )
    
    # Generate instructions based on status
    if interview and interview.status == InterviewStatus.COMPLETED:
        instructions = (
            "Your interview has been completed. Thank you for participating! "
            "You will receive feedback shortly."
        )
    elif interview and interview.status == InterviewStatus.IN_PROGRESS:
        instructions = (
            "Your interview is in progress. Please continue where you left off."
        )
    elif can_start:
        instructions = (
            "Welcome to your AI-powered interview! When you're ready:\n"
            "1. Ensure you're in a quiet environment\n"
            "2. Check your microphone is working\n"
            "3. Click 'Start Interview' to begin\n\n"
            "You'll be asked a series of questions. Speak clearly and take your time."
        )
    else:
        instructions = (
            "Your interview session is not yet ready. "
            "Please contact the recruiter for more information."
        )
    
    return PortalInfoResponse(
        candidate_id=candidate.candidate_id,
        name=candidate.name,
        email=candidate.email,
        job_title=job_title,
        interview_status=interview_status,
        interview_id=interview_id,
        can_start_interview=can_start,
        instructions=instructions,
    )


from app.api.routes.interview_routes import ensure_active_session

@router.post("/start-interview", response_model=StartInterviewResponse)
async def start_candidate_interview(
    candidate: AuthenticatedCandidate = Depends(require_candidate_session),
    db: AsyncSession = Depends(get_db),
):
    """
    Start an interview for the authenticated candidate.
    
    Requires X-Candidate-Session header with format: session_id:email
    """
    # Get candidate from database
    db_candidate = await db.get(Candidate, candidate.candidate_id)
    if not db_candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )
    
    # Get JD for initialization
    jd = await db.get(JobDescription, db_candidate.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Check if candidate can start interview
    if db_candidate.status not in (CandidateStatus.SHORTLISTED, CandidateStatus.FOCUS_READY):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot start interview. Candidate must be shortlisted first.",
        )
    
    # Check for existing interview
    result = await db.execute(
        select(Interview).where(Interview.candidate_id == candidate.candidate_id)
    )
    existing_interview = result.scalar_one_or_none()
    
    if existing_interview:
        if existing_interview.status == InterviewStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Interview already completed",
            )
        elif existing_interview.status == InterviewStatus.IN_PROGRESS:
            # Ensure session is active (restore or init)
            ensure_active_session(existing_interview, db_candidate, jd)
            await db.commit() # Save state if initialized
            
            return StartInterviewResponse(
                interview_id=existing_interview.interview_id,
                candidate_id=candidate.candidate_id,
                status=existing_interview.status.value,
                message="Resuming existing interview",
            )
        elif existing_interview.status == InterviewStatus.PENDING:
            # Start the pending interview
            existing_interview.status = InterviewStatus.IN_PROGRESS
            existing_interview.started_at = datetime.now(timezone.utc)
            db_candidate.status = CandidateStatus.INTERVIEWING
            await db.flush()
            
            # Ensure session is active
            ensure_active_session(existing_interview, db_candidate, jd)
            await db.commit()

            return StartInterviewResponse(
                interview_id=existing_interview.interview_id,
                candidate_id=candidate.candidate_id,
                status=existing_interview.status.value,
                message="Interview started",
            )
    
    # Create new interview
    interview = Interview(
        candidate_id=candidate.candidate_id,
        status=InterviewStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
    )
    db.add(interview)
    
    # Update candidate status
    db_candidate.status = CandidateStatus.INTERVIEWING
    
    await db.flush()
    
    # Initialize session
    ensure_active_session(interview, db_candidate, jd)
    await db.commit()
    
    logger.info(f"Interview started for candidate {candidate.candidate_id}")
    
    return StartInterviewResponse(
        interview_id=interview.interview_id,
        candidate_id=candidate.candidate_id,
        status=interview.status.value,
        message="Interview started successfully",
    )


@router.get("/interview/{interview_id}/status")
async def get_interview_status(
    interview_id: UUID,
    candidate: AuthenticatedCandidate = Depends(require_candidate_session),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of a candidate's interview."""
    interview = await db.get(Interview, interview_id)
    
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    # Verify the interview belongs to this candidate
    if interview.candidate_id != candidate.candidate_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "interview_id": interview.interview_id,
        "status": interview.status.value if interview.status else None,
        "current_pillar": interview.current_pillar,
        "question_number": interview.question_number,
        "total_questions": interview.total_questions,
        "started_at": interview.started_at,
        "ended_at": interview.ended_at,
    }


@router.websocket("/ws/{interview_id}")
async def candidate_interview_websocket(
    websocket: WebSocket,
    interview_id: str,
):
    """
    WebSocket endpoint for candidate interview with audio streaming.
    
    Protocol:
      Client → Server:
        - {"type": "audio_chunk", "data": {"chunk": "base64...", "sequence": N}}
        - {"type": "answer_complete"}
        
      Server → Client:
        - {"type": "question", "data": {...}}
        - {"type": "transcript", "data": {"text": "...", "is_partial": bool}}
        - {"type": "timer", "data": {"phase": "reading|answering", "seconds_remaining": N}}
        - {"type": "complete", "data": {...}}
    """
    await websocket.accept()
    
    try:
        # Validate session from query params or first message
        session_token = websocket.query_params.get("session")
        if not session_token:
            await websocket.send_json({
                "type": "error",
                "data": {"message": "Session token required"}
            })
            await websocket.close(code=4001)
            return
        
        # Parse session token
        try:
            parts = session_token.split(":", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            session_id, email = parts
        except Exception:
            await websocket.send_json({
                "type": "error",
                "data": {"message": "Invalid session token format"}
            })
            await websocket.close(code=4001)
            return
        
        # Note: In production, validate session against database
        # For now, just log the connection
        logger.info(f"Candidate WebSocket connected: interview={interview_id}")
        
        # Initialize transcribe service
        transcribe_service = get_transcribe_service()
        stream_id = await transcribe_service.start_stream(interview_id)
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "data": {
                "interview_id": interview_id,
                "message": "Connected to interview session"
            }
        })
        
        # Main message loop
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                msg_data = message.get("data", {})
                
                if msg_type == "audio_chunk":
                    # Process audio through transcribe
                    import base64
                    audio_bytes = base64.b64decode(msg_data.get("chunk", ""))
                    await transcribe_service.feed_audio(stream_id, audio_bytes)
                    
                elif msg_type == "answer_complete":
                    # Stop transcription and get final text
                    final_text = await transcribe_service.stop_stream(stream_id)
                    await websocket.send_json({
                        "type": "transcript",
                        "data": {
                            "text": final_text,
                            "is_partial": False,
                            "is_final": True,
                        }
                    })
                    
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except WebSocketDisconnect:
                logger.info(f"Candidate disconnected: interview={interview_id}")
                break
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=1011)
