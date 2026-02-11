"""
Production Interview Routes

API routes for interview management with:
- New LangGraph state machine architecture
- Real-time recruiter visibility via WebSocket
- Server-side timing enforcement
- Deterministic termination via decision router
"""

import asyncio
import json
import base64
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.database import get_db, async_session_factory
from app.models.models import (
    Candidate, Interview, Transcript, JobDescription,
    InterviewStatus, CandidateStatus,
    Evaluation, Report, Recommendation,
)
from app.schemas.schemas import InterviewStartRequest, InterviewResponse, InterviewProgress
from app.schemas.state import (
    InterviewState,
    InterviewPhase,
    RouterDecision,
    create_initial_state,
)
from app.services.graphs.interview_graph import build_interview_graph
from app.services.graphs.postgres_checkpoint import get_postgres_checkpointer
from app.services.realtime.interview_broadcaster import (
    get_broadcaster,
    InterviewEventType,
    create_interview_started_event,
    create_question_asked_event,
    create_answer_analyzed_event,
    create_cheating_flag_event,
    create_pillar_completed_event,
    create_interview_completed_event,
)

from app.services.aws.transcribe_service import get_transcribe_service
from app.services.aws.s3_service import get_s3_service
from app.api.middleware.auth_middleware import require_recruiter, AuthenticatedUser
from app.api.utils.db_utils import verify_interview_ownership
from app.core.config import get_settings
from app.core.logging import get_logger

# Shared Services imports
from app.services.realtime.session_manager import (
    active_sessions,
    register_session,
    get_session,
    remove_session,
    mark_terminated,
    schedule_cleanup,
)
from app.services.graphs.lifecycle import (
    ensure_active_session,
    run_post_interview_analysis,
    handle_disconnect_cleanup,
    delayed_disconnect_cleanup,
)
from app.services.graphs.execution import run_interview_event_loop

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/interviews", tags=["Interviews"])


# ═══════════════════════════════════════════════════════════════════════════════
# REST ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════




@router.post("/start", response_model=InterviewResponse)
async def start_interview(
    request: InterviewStartRequest,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Initialize an interview session for a candidate."""
    candidate = await db.get(Candidate, request.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if candidate.status not in (CandidateStatus.FOCUS_READY, CandidateStatus.SHORTLISTED):
        raise HTTPException(
            status_code=400,
            detail=f"Candidate status must be focus_ready or shortlisted, got {candidate.status.value}"
        )

    jd = await db.get(JobDescription, candidate.jd_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")
        
    # Verify ownership
    if jd.recruiter_id != user.recruiter_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Create interview record first to get ID
    interview = Interview(
        candidate_id=request.candidate_id,
        status=InterviewStatus.PENDING,
        current_pillar="Initializing",
    )
    db.add(interview)
    await db.flush()

    # Create production-grade initial state
    initial_state = create_initial_state(
        interview_id=str(interview.interview_id),
        candidate_id=str(candidate.candidate_id),
        jd_id=str(jd.jd_id),
        candidate_name=candidate.name,
        candidate_email=candidate.email,
        job_role=jd.title,
        job_requirements=jd.parsed_data or {},
        resume_context=candidate.resume_text or "",
        focus_areas=candidate.focus_areas or [],
        config={
            "reading_buffer_seconds": settings.READING_TIME_SECONDS,
            "answer_window_seconds": settings.ANSWER_TIME_SECONDS,
            "max_questions_per_pillar": settings.MAX_QUESTIONS_PER_TOPIC,
        },
    )

    # Store initial state in DB
    interview.state_json = dict(initial_state)
    await db.commit()

    logger.info(f"Interview created: {interview.interview_id} for candidate {candidate.name}")

    return InterviewResponse(
        interview_id=interview.interview_id,
        candidate_id=interview.candidate_id,
        status=interview.status.value,
        started_at=interview.started_at,
        current_pillar="Initializing",
        question_number=0,
        transcript=[],
    )


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get interview details with current state."""
    interview = await verify_interview_ownership(db, interview_id, user.recruiter_id)

    state = interview.state_json or {}

    # Get current pillar name
    focus_areas = state.get("focus_areas", [])
    current_idx = state.get("current_pillar_index", 0)
    current_pillar = "Unknown"
    if focus_areas and 0 <= current_idx < len(focus_areas):
        current_pillar = focus_areas[current_idx].get("skill", "Unknown")

    # Build transcript from question records
    transcript = []
    for record in state.get("question_records", []):
        transcript.append({
            "question": record.get("question_text"),
            "answer": record.get("answer_text"),
            "pillar": record.get("pillar_name"),
            "is_follow_up": record.get("is_follow_up", False),
        })

    return InterviewResponse(
        interview_id=interview.interview_id,
        candidate_id=interview.candidate_id,
        status=interview.status.value if interview.status else "pending",
        started_at=interview.started_at,
        current_pillar=current_pillar,
        question_number=state.get("total_questions_asked", 0),
        transcript=transcript,
    )


@router.get("/{interview_id}/progress")
async def get_progress(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get current interview progress for monitoring."""
    interview = await verify_interview_ownership(db, interview_id, user.recruiter_id)

    state = interview.state_json or {}
    is_active = str(interview_id) in active_sessions

    # Get current pillar name
    focus_areas = state.get("focus_areas", [])
    current_idx = state.get("current_pillar_index", 0)
    current_pillar = "Initializing"
    if focus_areas and 0 <= current_idx < len(focus_areas):
        current_pillar = focus_areas[current_idx].get("skill", "Unknown")

    return InterviewProgress(
        interview_id=interview_id,
        candidate_id=interview.candidate_id,
        status="in_progress" if is_active else (interview.status.value if interview.status else "pending"),
        current_pillar=current_pillar,
        question_number=state.get("total_questions_asked", 0),
        total_questions=state.get("max_total_questions", 25),
        cheating_level=state.get("cheating_level", "none"),
    )


@router.get("/monitor/active")
async def get_active_interviews(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get list of currently active interviews for live monitoring."""
    if not active_sessions:
        return []

    interview_ids = [UUID(k) for k in active_sessions.keys()]
    if not interview_ids:
        return []

    result = await db.execute(
        select(Interview)
        .join(Candidate, Interview.candidate_id == Candidate.candidate_id)
        .join(JobDescription, Candidate.jd_id == JobDescription.jd_id)
        .where(
            Interview.interview_id.in_(interview_ids),
            JobDescription.recruiter_id == user.recruiter_id
        )
    )
    interviews = result.scalars().all()

    stats = []
    for interview in interviews:
        candidate = await db.get(Candidate, interview.candidate_id)
        state = interview.state_json or {}

        # Get current pillar
        focus_areas = state.get("focus_areas", [])
        current_idx = state.get("current_pillar_index", 0)
        current_pillar = "Unknown"
        if focus_areas and 0 <= current_idx < len(focus_areas):
            current_pillar = focus_areas[current_idx].get("skill", "Unknown")

        phase = state.get("phase", InterviewPhase.INITIALIZING.value)

        stats.append({
            "interview_id": str(interview.interview_id),
            "candidate_name": candidate.name if candidate else "Unknown",
            "candidate_email": candidate.email if candidate else "",
            "current_pillar": current_pillar,
            "question_number": state.get("total_questions_asked", 0),
            "cheating_level": state.get("cheating_level", "none"),
            "phase": phase,
            "status": "completed" if phase in [InterviewPhase.COMPLETED.value, InterviewPhase.TERMINATED.value] else "in_progress",
        })

    return stats


@router.post("/{interview_id}/terminate")
async def terminate_interview(
    interview_id: UUID,
    reason: str = "Recruiter requested termination",
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Terminate an interview immediately (recruiter action)."""
    interview = await verify_interview_ownership(db, interview_id, user.recruiter_id)

    if interview.status in [InterviewStatus.COMPLETED, InterviewStatus.TERMINATED]:
        raise HTTPException(status_code=400, detail="Interview already ended")

    # Mark for termination
    interview.status = InterviewStatus.TERMINATED
    interview.ended_at = datetime.now(timezone.utc)

    # Update state
    state = interview.state_json or {}
    term_conditions = state.get("termination_conditions", {})
    term_conditions["recruiter_terminated"] = True
    term_conditions["recruiter_termination_reason"] = reason
    state["termination_conditions"] = term_conditions
    state["phase"] = InterviewPhase.TERMINATED.value
    interview.state_json = state

    await db.commit()

    # Signal active session
    if str(interview_id) in active_sessions:
        mark_terminated(str(interview_id))

    # Broadcast termination
    broadcaster = get_broadcaster()
    await broadcaster.broadcast(
        str(interview_id),
        InterviewEventType.INTERVIEW_TERMINATED,
        {"reason": reason, "terminated_by": "recruiter"},
    )

    logger.info(f"Interview {interview_id} terminated by recruiter: {reason}")

    return {"status": "terminated", "reason": reason}


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET INTERVIEW SESSION
# ═══════════════════════════════════════════════════════════════════════════════


@router.websocket("/ws/{interview_id}")
async def interview_websocket(websocket: WebSocket, interview_id: str):
    """
    WebSocket endpoint for live interview streaming.

    Uses the production LangGraph architecture with:
    - Deterministic decision routing
    - Server-side timing enforcement
    - Real-time recruiter broadcasting
    - Automatic state persistence
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for interview {interview_id}")

    # Register active session (also cancels any pending cleanup)
    register_session(interview_id, websocket)

    transcribe_service = get_transcribe_service()
    broadcaster = get_broadcaster()

    # Initialize checkpointer and graph
    checkpointer = await get_postgres_checkpointer()
    graph = build_interview_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": interview_id}}

    # Load/seed state from DB
    async with async_session_factory() as db:
        interview = await db.get(Interview, UUID(interview_id))
        if not interview:
            await websocket.send_json({"type": "error", "data": {"message": "Interview not found"}})
            await websocket.close()
            return

        candidate = await db.get(Candidate, interview.candidate_id)
        jd = await db.get(JobDescription, candidate.jd_id) if candidate else None

        # CRITICAL: Always sync graph state from DB on reconnect to prevent question repetition
        # The graph checkpointer and DB can get out of sync, especially after refresh
        current_state_snap = await graph.aget_state(config)

        if interview.state_json:
            # Compare checkpoint state with DB state
            db_state = interview.state_json
            checkpoint_state = current_state_snap.values if current_state_snap else None

            # If no checkpoint state OR if DB has more recent questions, resync
            should_resync = False
            if not checkpoint_state:
                should_resync = True
                logger.info(f"No checkpoint state found for {interview_id}, seeding from DB")
            else:
                db_question_count = len(db_state.get("question_records", []))
                checkpoint_question_count = len(checkpoint_state.get("question_records", []))
                if db_question_count > checkpoint_question_count:
                    should_resync = True
                    logger.warning(
                        f"DB has more questions ({db_question_count}) than checkpoint ({checkpoint_question_count}). "
                        f"Resyncing to prevent repetition."
                    )

            if should_resync:
                await graph.aupdate_state(config, db_state)
                logger.info(f"Synced graph state from DB for {interview_id}")
                # Refresh state snapshot after update
                current_state_snap = await graph.aget_state(config)

        # Update interview status
        if interview.status == InterviewStatus.PENDING:
            interview.status = InterviewStatus.IN_PROGRESS
            interview.started_at = interview.started_at or datetime.now(timezone.utc)
            await db.commit()

        # Restore state to client
        if current_state_snap and current_state_snap.values:
            state = current_state_snap.values
            
            # 1. Build Transcript
            transcript = []
            for record in state.get("question_records", []):
                if record.get("answer_text") or record.get("answer_audio_url"):
                    transcript.append({
                        "q": record.get("question_text", ""),
                        "a": record.get("answer_text") or "(Audio Answer)"
                    })
            
            # 2. Calculate Phase and Time Left
            current_phase = state.get("phase", "idle")
            time_left = 0
            
            timing = state.get("timing", {})
            now = datetime.now(timezone.utc)
            
            if current_phase == "reading" and "reading_deadline" in timing:
                deadline = datetime.fromisoformat(timing["reading_deadline"])
                time_left = max(0, int((deadline - now).total_seconds()))
            elif current_phase == "answering" and "answer_deadline" in timing:
                deadline = datetime.fromisoformat(timing["answer_deadline"])
                time_left = max(0, int((deadline - now).total_seconds()))
                
            # 3. Current Question Data
            restore_data = {
                "transcript": transcript,
                "phase": current_phase,
                "time_left": time_left,
            }
            
            if state.get("current_question"):
                # Reconstruct question object
                current_idx = state.get("current_pillar_index", 0)
                focus_areas = state.get("focus_areas", [])
                pillar_name = "Unknown"
                if focus_areas and 0 <= current_idx < len(focus_areas):
                    pillar_name = focus_areas[current_idx].get("skill", "Unknown")
                    
                restore_data["question"] = {
                    "question_text": state.get("current_question"),
                    "pillar": pillar_name,
                    "question_number": state.get("total_questions_asked", 1),
                    "depth_level": state.get("current_question_depth", 1),
                    "is_follow_up": state.get("follow_ups_in_current_pillar", 0) > 0,
                    "reading_time_seconds": settings.READING_TIME_SECONDS,
                    "answer_time_seconds": settings.ANSWER_TIME_SECONDS,
                }

            logger.info(f"Sending restore_state to {interview_id}: {len(transcript)} items")
            await websocket.send_json({
                "type": "restore_state",
                "data": restore_data
            })

    # Re-register session to ensure fields are up to date after state restore
    register_session(interview_id, websocket)

    # Broadcast interview started
    await broadcaster.broadcast(
        interview_id,
        InterviewEventType.INTERVIEW_STARTED,
        create_interview_started_event(
            interview_id=interview_id,
            candidate_name=candidate.name if candidate else "Unknown",
            job_role=jd.title if jd else "Unknown",
            total_pillars=len(interview.state_json.get("focus_areas", [])) if interview.state_json else 0,
        ),
    )

    try:
        await run_interview_event_loop(
            graph, config, websocket, interview_id, transcribe_service, broadcaster
        )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {interview_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {interview_id}: {e}", exc_info=True)
    finally:
        # Cleanup session tracking
        remove_session(interview_id)

        # Schedule delayed cleanup instead of immediate
        # This allows the user to refresh the page without terminating the interview
        task = asyncio.create_task(delayed_disconnect_cleanup(interview_id, broadcaster))
        schedule_cleanup(interview_id, task)
        
        logger.info(f"WebSocket disconnected for {interview_id}, cleanup scheduled")





# ═══════════════════════════════════════════════════════════════════════════════
# RECRUITER MONITORING WEBSOCKET
# ═══════════════════════════════════════════════════════════════════════════════


@router.websocket("/ws/monitor/{interview_id}")
async def recruiter_monitor_websocket(
    websocket: WebSocket,
    interview_id: str,
    recruiter_id: str = "default",
):
    """WebSocket for recruiters to monitor live interviews."""
    broadcaster = get_broadcaster()

    try:
        connection = await broadcaster.connect(
            websocket=websocket,
            interview_id=interview_id,
            recruiter_id=recruiter_id,
        )

        # Send initial state
        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if interview:
                state = interview.state_json or {}
                await websocket.send_json({
                    "type": "initial_state",
                    "data": {
                        "phase": state.get("phase", "unknown"),
                        "question_number": state.get("total_questions_asked", 0),
                        "current_pillar_index": state.get("current_pillar_index", 0),
                        "cheating_level": state.get("cheating_level", "none"),
                    }
                })

        # Keep connection alive
        while True:
            try:
                # Ping/pong to keep alive
                await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(connection, interview_id)
