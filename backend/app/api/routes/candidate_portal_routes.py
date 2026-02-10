"""Candidate Portal routes for session-based login and interview access."""

import asyncio
from uuid import UUID
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db, async_session_factory
from app.core.config import get_settings
from app.models.models import Candidate, JobDescription, Interview, InterviewStatus, CandidateStatus, Transcript
from app.api.middleware.auth_middleware import (
    require_candidate_session,
    AuthenticatedCandidate,
)
from app.services.aws.transcribe_service import get_transcribe_service
from app.services.realtime.interview_broadcaster import (
    get_broadcaster,
    InterviewEventType,
    create_interview_started_event,
)
from app.core.logging import get_logger

# Shared Services
from app.services.realtime.session_manager import active_sessions, pending_cleanups
from app.services.graphs.lifecycle import (
    ensure_active_session,
    delayed_disconnect_cleanup
)
from app.services.graphs.execution import (
    run_graph_cycle,
    handle_answer_started,
    handle_answer_complete,
    handle_violation,
    handle_request_finish,
)
from app.services.graphs.interview_graph import build_interview_graph
from app.services.graphs.postgres_checkpoint import get_postgres_checkpointer

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
        if existing_interview.status in [InterviewStatus.COMPLETED, InterviewStatus.TERMINATED]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Interview already completed or terminated",
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
    
    Uses shared execution logic (Graph) and session management.
    Requires 'session' query parameter with format: session_id:email
    """
    await websocket.accept()
    
    # 1. Validate Session
    session_token = websocket.query_params.get("session")
    if not session_token:
        await websocket.close(code=4003, reason="Session token required")
        return

    try:
        # Basic format check (In production, verify against DB/SessionStore)
        parts = session_token.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Invalid format")
        session_id, email = parts
    except Exception:
        await websocket.close(code=4003, reason="Invalid session token")
        return

    logger.info(f"Candidate WebSocket connected: interview={interview_id}, email={email}")

    # 2. Setup Services
    transcribe_service = get_transcribe_service()
    broadcaster = get_broadcaster()
    
    # Cancel any pending cleanup (reconnection)
    if interview_id in pending_cleanups:
        logger.info(f"Cancelling pending cleanup for {interview_id} - reconnected")
        pending_cleanups[interview_id].cancel()
        pending_cleanups.pop(interview_id, None)

    # Register active session
    active_sessions[interview_id] = {
        "websocket": websocket,
        "connected_at": datetime.now(timezone.utc),
        "stream_id": f"stream-{interview_id}",
        "answer_buffer": "",
        "terminated": False,
        "user_email": email # Metadata
    }

    try:
        # 3. Initialize Graph & State
        checkpointer = await get_postgres_checkpointer()
        graph = build_interview_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": interview_id}}

        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if not interview:
                await websocket.send_json({"type": "error", "data": {"message": "Interview not found"}})
                await websocket.close()
                return
            
            # Verify candidate ownership (Double check)
            candidate = await db.get(Candidate, interview.candidate_id)
            if not candidate or candidate.email != email:
                logger.warning(f"Session email {email} does not match candidate {candidate.email if candidate else 'None'}")
                await websocket.close(code=4003, reason="Unauthorized")
                return

            jd = await db.get(JobDescription, candidate.jd_id)

            # CRITICAL: Prevent restarting completed/terminated interviews
            if interview.status in [InterviewStatus.COMPLETED, InterviewStatus.TERMINATED]:
                logger.warning(f"Attempt to connect to completed/terminated interview {interview_id}")
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": "Interview already completed"}
                })
                await websocket.close(code=4003, reason="Interview already completed")
                return

            # Ensure graph state is consistent
            current_state_snap = await graph.aget_state(config)
            if not current_state_snap or not current_state_snap.values:
                if interview.state_json:
                    await graph.aupdate_state(config, interview.state_json)
                    logger.info(f"Seeded graph state from DB for {interview_id}")

            # Update status if needed
            if interview.status == InterviewStatus.PENDING:
                interview.status = InterviewStatus.IN_PROGRESS
                interview.started_at = interview.started_at or datetime.now(timezone.utc)
                await db.commit()

            # Restore State to Client
            if current_state_snap and current_state_snap.values:
                state = current_state_snap.values
                
                # Build Transcript
                transcript = []
                for record in state.get("question_records", []):
                    if record.get("answer_text") or record.get("answer_audio_url"):
                        transcript.append({
                            "q": record.get("question_text", ""),
                            "a": record.get("answer_text") or "(Audio Answer)"
                        })
                
                # Current Question
                restore_data = {
                    "transcript": transcript,
                    "phase": state.get("phase", "idle"),
                }
                
                if state.get("current_question"):
                    # Reconstruct question info
                    current_idx = state.get("current_pillar_index", 0)
                    focus_areas = state.get("focus_areas", [])
                    pillar_name = focus_areas[current_idx].get("skill", "Unknown") if focus_areas and 0 <= current_idx < len(focus_areas) else "Unknown"

                    restore_data["question"] = {
                        "question_text": state.get("current_question"),
                        "pillar": pillar_name,
                        "question_number": state.get("total_questions_asked", 1),
                        "depth_level": state.get("current_question_depth", 1),
                        "is_follow_up": state.get("follow_ups_in_current_pillar", 0) > 0,
                        "reading_time_seconds": settings.READING_TIME_SECONDS,
                        "answer_time_seconds": settings.ANSWER_TIME_SECONDS,
                    }

                await websocket.send_json({
                    "type": "restore_state",
                    "data": restore_data
                })

        # Broadcast Started/Resumed
        await broadcaster.broadcast(
            interview_id,
            InterviewEventType.INTERVIEW_STARTED,
            create_interview_started_event(
                interview_id=interview_id,
                candidate_name=candidate.name,
                job_role=jd.title if jd else "Unknown",
                total_pillars=len(interview.state_json.get("focus_areas", [])) if interview.state_json else 0,
            ),
        )

        # 4. Main Event Loop
        while True:
            # Check for termination flag in session
            session = active_sessions.get(interview_id, {})
            if session.get("terminated"):
                await websocket.send_json({
                    "type": "terminated",
                    "data": {"message": "Interview terminated by recruiter"}
                })
                break

            # Receive
            raw_msg = await websocket.receive_text()
            import json
            msg = json.loads(raw_msg)
            msg_type = msg.get("type", "")

            # Dispatch to Execution Service
            if msg_type == "start":
                await run_graph_cycle(graph, config, websocket, interview_id, broadcaster)

            elif msg_type == "audio_chunk":
                chunk_data = msg.get("data", {})
                import base64
                audio_bytes = base64.b64decode(chunk_data.get("chunk", ""))
                stream_id = active_sessions[interview_id]["stream_id"]
                
                # Start stream if needed
                if not transcribe_service.is_active(stream_id):
                    async def on_partial(text):
                        if interview_id in active_sessions:
                            await websocket.send_json({
                                "type": "transcript_partial",
                                "data": {"text": text}
                            })
                    await transcribe_service.start_stream(interview_id, on_partial=on_partial)

                await transcribe_service.feed_audio(stream_id, audio_bytes)

            elif msg_type == "answer_started":
                await handle_answer_started(graph, config, interview_id)

            elif msg_type == "answer_complete":
                await handle_answer_complete(
                    graph, config, websocket, interview_id, 
                    msg.get("data", {}), transcribe_service, broadcaster
                )

            elif msg_type == "violation":
                 await handle_violation(
                    graph, config, interview_id,
                    msg.get("data", {}), broadcaster
                )
            
            elif msg_type == "request_finish":
                await handle_request_finish(websocket, interview_id, broadcaster)
                break
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"Candidate disconnected: {interview_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Cleanup
        active_sessions.pop(interview_id, None)
        task = asyncio.create_task(delayed_disconnect_cleanup(interview_id, broadcaster))
        pending_cleanups[interview_id] = task
