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
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.database import get_db, async_session_factory
from app.models.models import (
    Candidate, Interview, Transcript, JobDescription,
    InterviewStatus, CandidateStatus, CheatingLevel,
    Evaluation, Report, Recommendation,
)
from app.schemas.schemas import InterviewStartRequest, InterviewResponse, InterviewProgress
from app.schemas.state import (
    InterviewState,
    InterviewPhase,
    RouterDecision,
    create_initial_state,
)
from app.services.graphs.interview_graph import (
    build_interview_graph,
    create_interview_session,
    resume_with_answer,
    request_termination,
)
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

def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to serialize LangGraph state for JSON storage."""
    serialized = {}
    for k, v in state.items():
        if isinstance(v, list):
            new_list = []
            for item in v:
                if hasattr(item, "model_dump"):
                    new_list.append(item.model_dump())
                elif hasattr(item, "dict"):
                    new_list.append(item.dict())
                else:
                    new_list.append(item)
            serialized[k] = new_list
        elif hasattr(v, "model_dump"):
            serialized[k] = v.model_dump()
        elif hasattr(v, "dict"):
            serialized[k] = v.dict()
        else:
            serialized[k] = v
    return serialized
from app.services.aws.transcribe_service import get_transcribe_service
from app.services.aws.s3_service import get_s3_service
from app.api.middleware.auth_middleware import require_recruiter, AuthenticatedUser
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/interviews", tags=["Interviews"])

# Active interview sessions (WebSocket connections)
active_sessions: Dict[str, Dict[str, Any]] = {}

# Pending cleanup tasks for disconnected sessions to allow grace period for refresh
pending_cleanups: Dict[str, asyncio.Task] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# REST ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


def ensure_active_session(
    interview: Interview,
    candidate: Candidate,
    jd: JobDescription,
):
    """
    Ensure the interview session is properly initialized with state.
    Used by both recruiter start and candidate portal resume.
    """
    if not interview.state_json:
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
        interview.state_json = dict(initial_state)

    if interview.status == InterviewStatus.PENDING:
        interview.status = InterviewStatus.IN_PROGRESS
        interview.started_at = datetime.now(timezone.utc)


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
    # Join with Candidate -> JD to verify ownership
    query = (
        select(Interview)
        .join(Candidate, Interview.candidate_id == Candidate.candidate_id)
        .join(JobDescription, Candidate.jd_id == JobDescription.jd_id)
        .where(
            Interview.interview_id == interview_id,
            JobDescription.recruiter_id == user.recruiter_id
        )
    )
    result = await db.execute(query)
    interview = result.scalar_one_or_none()
    
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

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
    # Join with Candidate -> JD to verify ownership
    query = (
        select(Interview)
        .join(Candidate, Interview.candidate_id == Candidate.candidate_id)
        .join(JobDescription, Candidate.jd_id == JobDescription.jd_id)
        .where(
            Interview.interview_id == interview_id,
            JobDescription.recruiter_id == user.recruiter_id
        )
    )
    result = await db.execute(query)
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

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
    # Join with Candidate -> JD to verify ownership
    query = (
        select(Interview)
        .join(Candidate, Interview.candidate_id == Candidate.candidate_id)
        .join(JobDescription, Candidate.jd_id == JobDescription.jd_id)
        .where(
            Interview.interview_id == interview_id,
            JobDescription.recruiter_id == user.recruiter_id
        )
    )
    result = await db.execute(query)
    interview = result.scalar_one_or_none()

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

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
        active_sessions[str(interview_id)]["terminated"] = True

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

    # Cancel any pending cleanup for this interview (user returned)
    if interview_id in pending_cleanups:
        logger.info(f"Cancelling pending cleanup for {interview_id} - reconnected")
        pending_cleanups[interview_id].cancel()
        pending_cleanups.pop(interview_id, None)

    # Register active session
    active_sessions[interview_id] = {"websocket": websocket, "connected_at": datetime.now(timezone.utc)}

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

        # Check if graph has state, if not seed from DB
        current_state_snap = await graph.aget_state(config)
        if not current_state_snap or not current_state_snap.values:
            if interview.state_json:
                await graph.aupdate_state(config, interview.state_json)
                logger.info(f"Seeded graph state from DB for {interview_id}")

        # Update interview status
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
            now = datetime.utcnow()
            
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

    # Register active session
    active_sessions[interview_id] = {
        "websocket": websocket,
        "terminated": False,
        "stream_id": f"stream-{interview_id}",
        "answer_buffer": "",
    }

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
        while True:
            # Check for termination
            session = active_sessions.get(interview_id, {})
            if session.get("terminated"):
                await websocket.send_json({
                    "type": "terminated",
                    "data": {"message": "Interview terminated by recruiter"}
                })
                break

            # Receive message
            raw_msg = await websocket.receive_text()
            msg = json.loads(raw_msg)
            msg_type = msg.get("type", "")

            if msg_type == "start":
                # Start or resume the interview graph
                await _run_graph_cycle(
                    graph, config, websocket, interview_id, broadcaster
                )

            elif msg_type == "audio_chunk":
                # Process audio chunk for transcription
                chunk_data = msg.get("data", {})
                audio_bytes = base64.b64decode(chunk_data.get("chunk", ""))
                stream_id = active_sessions[interview_id]["stream_id"]
                
                # Start stream if not active
                if not transcribe_service.is_active(stream_id):
                    async def on_partial(text):
                        try:
                            # Verify session is still active/valid
                            if interview_id in active_sessions:
                                await websocket.send_json({
                                    "type": "transcript_partial",
                                    "data": {"text": text}
                                })
                        except Exception as e:
                            logger.error(f"Failed to send partial transcript: {e}")

                    await transcribe_service.start_stream(
                        interview_id,
                        on_partial=on_partial
                    )

                await transcribe_service.feed_audio(stream_id, audio_bytes)

            elif msg_type == "answer_started":
                # Candidate started answering (after reading period)
                await _handle_answer_started(graph, config, interview_id)

            elif msg_type == "answer_complete":
                # Process completed answer
                await _handle_answer_complete(
                    graph, config, websocket, interview_id,
                    msg.get("data", {}), transcribe_service, broadcaster
                )

            elif msg_type == "violation":
                # Handle cheating/violation report
                await _handle_violation(
                    graph, config, interview_id,
                    msg.get("data", {}), broadcaster
                )

            elif msg_type == "request_finish":
                # Candidate requested to finish interview early
                logger.info(f"Candidate requested finish for {interview_id}")
                
                # Update DB status
                async with async_session_factory() as db:
                    interview = await db.get(Interview, UUID(interview_id))
                    if interview:
                        interview.status = InterviewStatus.COMPLETED
                        interview.ended_at = datetime.now(timezone.utc)
                        await db.commit()

                # Trigger post-interview analysis
                asyncio.create_task(_run_post_interview_analysis(interview_id))
                
                # Send completion message
                await websocket.send_json({
                    "type": "complete",
                    "data": {
                        "message": "Interview completed by user request",
                        "reason": "user_completed",
                    }
                })
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {interview_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {interview_id}: {e}", exc_info=True)
    finally:
        # Cleanup session tracking
        active_sessions.pop(interview_id, None)

        # Schedule delayed cleanup instead of immediate
        # This allows the user to refresh the page without terminating the interview
        task = asyncio.create_task(delayed_disconnect_cleanup(interview_id, broadcaster))
        pending_cleanups[interview_id] = task
        
        logger.info(f"WebSocket disconnected for {interview_id}, cleanup scheduled")


async def _run_graph_cycle(
    graph,
    config: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    broadcaster,
):
    """Run a graph execution cycle and handle events."""
    try:
        async for event in graph.astream(None, config, stream_mode="updates"):
            await _handle_graph_event(
                event, websocket, interview_id, broadcaster
            )

            # Check if we hit an interrupt point
            state_snap = await graph.aget_state(config)
            if state_snap and state_snap.next:
                # Graph is waiting for input (audio_pipeline interrupt)
                break

    except Exception as e:
        logger.error(f"Graph cycle error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"Graph error: {str(e)}"}
        })


async def _handle_graph_event(
    event: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    broadcaster,
):
    for node_name, state_update in event.items():
        # logger.info(f"Handling graph event from node: {node_name}. Keys: {list(state_update.keys())}")
        if node_name == "question_engine":
            # New question generated
            question = state_update.get("current_question")
            if question:
                # Get pillar info
                focus_areas = state_update.get("focus_areas", [])
                current_idx = state_update.get("current_pillar_index", 0)
                pillar_name = "Unknown"
                if focus_areas and 0 <= current_idx < len(focus_areas):
                    pillar_name = focus_areas[current_idx].get("skill", "Unknown")

                await websocket.send_json({
                    "type": "question",
                    "data": {
                        "question_text": question,
                        "pillar": pillar_name,
                        "question_number": state_update.get("total_questions_asked", 1),
                        "depth_level": state_update.get("current_question_depth", 1),
                        "is_follow_up": state_update.get("follow_ups_in_current_pillar", 0) > 0,
                        "reading_time_seconds": settings.READING_TIME_SECONDS,
                        "answer_time_seconds": settings.ANSWER_TIME_SECONDS,
                    }
                })

                # Broadcast to recruiters
                await broadcaster.broadcast(
                    interview_id,
                    InterviewEventType.QUESTION_ASKED,
                    create_question_asked_event(
                        question_number=state_update.get("total_questions_asked", 1),
                        pillar_name=pillar_name,
                        pillar_index=current_idx,
                        question_preview=question[:100],
                        depth_level=state_update.get("current_question_depth", 1),
                        is_follow_up=state_update.get("follow_ups_in_current_pillar", 0) > 0,
                    ),
                )

        elif node_name == "pillar_manager":
            # Pillar transition
            phase = state_update.get("phase")
            if phase == InterviewPhase.TRANSITIONING.value:
                focus_areas = state_update.get("focus_areas", [])
                current_idx = state_update.get("current_pillar_index", 0)

                if current_idx > 0 and current_idx <= len(focus_areas):
                    prev_pillar = focus_areas[current_idx - 1]
                    next_pillar = focus_areas[current_idx] if current_idx < len(focus_areas) else None

                    await websocket.send_json({
                        "type": "pillar_transition",
                        "data": {
                            "completed_pillar": prev_pillar.get("skill"),
                            "next_pillar": next_pillar.get("skill") if next_pillar else None,
                        }
                    })

                    await broadcaster.broadcast(
                        interview_id,
                        InterviewEventType.PILLAR_COMPLETED,
                        create_pillar_completed_event(
                            pillar_name=prev_pillar.get("skill", "Unknown"),
                            pillar_index=current_idx - 1,
                            pillar_score=prev_pillar.get("pillar_score", 0),
                            questions_asked=prev_pillar.get("questions_asked", 0),
                            next_pillar=next_pillar.get("skill") if next_pillar else None,
                        ),
                    )

        elif node_name == "answer_analyzer":
            # Answer analyzed
            signals = state_update.get("last_analysis_signals", {})
            if signals:
                await broadcaster.broadcast(
                    interview_id,
                    InterviewEventType.ANSWER_ANALYZED,
                    create_answer_analyzed_event(
                        question_number=state_update.get("total_questions_asked", 0),
                        pillar_name=state_update.get("current_pillar", "Unknown"),
                        score=signals.get("overall_signal_score", 0),
                        summary=signals.get("analysis_summary", ""),
                        has_concerns=signals.get("has_probeable_gaps", False),
                    ),
                )

            # Check for cheating flags
            cheating_level = state_update.get("cheating_level")
            if cheating_level and cheating_level != "none":
                await broadcaster.broadcast(
                    interview_id,
                    InterviewEventType.CHEATING_FLAG,
                    create_cheating_flag_event(
                        question_number=state_update.get("total_questions_asked", 0),
                        severity=cheating_level,
                        reason=state_update.get("cheating_flags", [{}])[-1].get("reason", ""),
                        cumulative_score=state_update.get("cheating_score", 0),
                    ),
                )

        elif node_name == "decision_router":
            # Routing decision
            decision = state_update.get("router_decision")
            phase = state_update.get("phase")

            if decision in [
                RouterDecision.END_COMPLETE.value,
                RouterDecision.END_VIOLATION.value,
                RouterDecision.END_TIMEOUT.value,
                RouterDecision.END_RECRUITER.value,
            ]:
                await websocket.send_json({
                    "type": "complete",
                    "data": {
                        "message": "Interview completed",
                        "reason": decision,
                    }
                })

                # Update DB
                async with async_session_factory() as db:
                    interview = await db.get(Interview, UUID(interview_id))
                    if interview:
                        interview.status = (
                            InterviewStatus.COMPLETED
                            if decision == RouterDecision.END_COMPLETE.value
                            else InterviewStatus.TERMINATED
                        )
                        interview.ended_at = datetime.now(timezone.utc)
                        interview.state_json = serialize_state(state_update)
                        await db.commit()

                # Broadcast completion
                timing = state_update.get("timing", {})
                started_at = timing.get("interview_started_at")
                duration = 0
                if started_at:
                    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    duration = (datetime.now(timezone.utc) - start).total_seconds() / 60

                await broadcaster.broadcast(
                    interview_id,
                    InterviewEventType.INTERVIEW_COMPLETED,
                    create_interview_completed_event(
                        completion_status=decision,
                        total_questions=state_update.get("total_questions_asked", 0),
                        total_pillars=state_update.get("total_pillars", 0),
                        duration_minutes=duration,
                        final_score=None,  # Calculated later in evaluation
                    ),
                )

                # Trigger post-interview analysis
                asyncio.create_task(_run_post_interview_analysis(interview_id))


async def _handle_answer_started(graph, config: Dict[str, Any], interview_id: str):
    """Handle when candidate starts answering."""
    # Update timing state
    now = datetime.now(timezone.utc)

    state_snap = await graph.aget_state(config)
    if state_snap and state_snap.values:
        timing = state_snap.values.get("timing", {})
        timing["answer_started_at"] = now.isoformat()
        await graph.aupdate_state(config, {"timing": timing})


async def _handle_answer_complete(
    graph,
    config: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    data: Dict[str, Any],
    transcribe_service,
    broadcaster,
):
    """Handle completed answer submission."""
    session = active_sessions.get(interview_id, {})
    stream_id = session.get("stream_id", f"stream-{interview_id}")

    # Get final transcription
    final_text = await transcribe_service.stop_stream(stream_id)
    user_text = data.get("text", "")
    final_answer = user_text or final_text or "(No answer provided)"

    # Get audio URL if we stored it
    audio_url = data.get("audio_url")

    # Update state with answer
    await graph.aupdate_state(config, {
        "_injected_answer_text": final_answer,
        "_injected_audio_url": audio_url,
    })

    # Resume graph (audio_pipeline → answer_analyzer → decision_router)
    await _run_graph_cycle(graph, config, websocket, interview_id, broadcaster)

    # Sync state to DB
    state_snap = await graph.aget_state(config)
    if state_snap and state_snap.values:
        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if interview:
                interview.state_json = serialize_state(dict(state_snap.values))
                
                # Persist Transcript for Analytics/Reporting
                # We do this here to ensure it's saved even if graph crashes later
                question_records = state_snap.values.get("question_records", [])
                if question_records:
                    last = question_records[-1]
                    # Only save if we have an answer and it hasn't been saved yet (check question_id?)
                    # Ideally we should check if transcript exists, but for now we assume 1-to-1 if linear
                    # We can use update_or_create logic or just append. 
                    # Let's check if it exists first to avoid duplicates on retries.
                    
                    # Check if transcript already exists for this question
                    existing_transcript = await db.execute(
                        select(Transcript).where(
                            Transcript.interview_id == interview.interview_id,
                            Transcript.question == last.get("question_text") # Using text as proxy if ID mismatch?
                            # Better to use question_id if available, but question_records might generate new IDs on retry?
                            # Actually question_records come from state.
                        )
                    )
                    if not existing_transcript.scalars().first():
                         # Clean up audio url
                         audio = last.get("answer_audio_url")
                         if audio and audio.startswith("http"):
                             pass # usage?
                         
                         transcript_entry = Transcript(
                            interview_id=interview.interview_id,
                            pillar=last.get("pillar_name", "General"),
                            question_number=state_snap.values.get("total_questions_asked", 0),
                            question=last.get("question_text", ""),
                            answer=last.get("answer_text", "(No answer)"),
                            audio_url=last.get("answer_audio_url"),
                            is_follow_up=last.get("is_follow_up", False),
                            created_at=datetime.now(timezone.utc)
                         )
                         db.add(transcript_entry)
                
                await db.commit()


async def _handle_violation(
    graph,
    config: Dict[str, Any],
    interview_id: str,
    data: Dict[str, Any],
    broadcaster,
):
    """Handle cheating/violation report."""
    violation_type = data.get("type", "unknown")
    details = data.get("details", "")

    # Update cheating flags in state
    state_snap = await graph.aget_state(config)
    if state_snap and state_snap.values:
        state = state_snap.values
        cheating_flags = state.get("cheating_flags", [])
        cheating_flags.append({
            "question_id": state.get("current_question_id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": f"{violation_type}: {details}",
            "severity": 7.0,  # High severity for manual reports
        })

        cheating_score = state.get("cheating_score", 0) + 3.0
        cheating_level = state.get("cheating_level", "none")

        if cheating_score >= 8.0:
            cheating_level = "penalty"
        elif cheating_score >= 6.0:
            cheating_level = "warning_2"
        elif cheating_score >= 4.0:
            cheating_level = "warning_1"

        await graph.aupdate_state(config, {
            "cheating_flags": cheating_flags,
            "cheating_score": cheating_score,
            "cheating_level": cheating_level,
        })

        # Broadcast
        await broadcaster.broadcast(
            interview_id,
            InterviewEventType.CHEATING_WARNING,
            {
                "type": violation_type,
                "details": details,
                "level": cheating_level,
                "cumulative_score": cheating_score,
            },
        )


async def _handle_disconnect_cleanup(interview_id: str, broadcaster):
    """Handle cleanup when WebSocket disconnects."""
    try:
        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if interview and interview.status in (
                InterviewStatus.PENDING,
                InterviewStatus.IN_PROGRESS,
            ):
                logger.info(f"Auto-completing disconnected interview: {interview_id}")
                interview.status = InterviewStatus.COMPLETED
                interview.ended_at = datetime.now(timezone.utc)
                await db.commit()

                # Trigger post-interview analysis
                asyncio.create_task(_run_post_interview_analysis(interview_id))

                # Broadcast
                await broadcaster.broadcast(
                    interview_id,
                    InterviewEventType.INTERVIEW_COMPLETED,
                    {
                        "completion_status": "disconnected",
                        "message": "Interview completed due to disconnection",
                    },
                )

    except Exception as e:
        logger.error(f"Disconnect cleanup failed for {interview_id}: {e}")


async def delayed_disconnect_cleanup(interview_id: str, broadcaster, delay: int = 15):
    """
    Wait for a grace period before cleaning up a disconnected session.
    If the user reconnects within the delay, this task should be cancelled.
    """
    try:
        await asyncio.sleep(delay)
        # Check if user reconnected (is in active_sessions)
        if interview_id not in active_sessions:
            logger.info(f"Grace period expired for {interview_id}, performing cleanup")
            await _handle_disconnect_cleanup(interview_id, broadcaster)
        else:
            logger.info(f"User reconnected for {interview_id}, skipping cleanup")
    except asyncio.CancelledError:
        logger.info(f"Cleanup cancelled for interview {interview_id} - user reconnected")
    finally:
        pending_cleanups.pop(interview_id, None)


async def _run_post_interview_analysis(interview_id: str):
    """Run evaluation and reporting graphs after interview completion."""
    logger.info(f"Starting post-interview analysis for {interview_id}")

    try:
        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if not interview:
                return

            candidate = await db.get(Candidate, interview.candidate_id)
            jd = await db.get(JobDescription, candidate.jd_id) if candidate else None

            if not candidate or not jd:
                logger.error(f"Missing candidate/JD for interview {interview_id}")
                return

            # Get transcript history from state
            state = interview.state_json or {}
            question_records = state.get("question_records", [])

            # Convert to transcript format for evaluation
            transcript_history = [
                {
                    "pillar": r.get("pillar_name"),
                    "question": r.get("question_text"),
                    "answer": r.get("answer_text"),
                    "is_follow_up": r.get("is_follow_up", False),
                }
                for r in question_records
                if r.get("answer_text")
            ]

            # Clear previous evaluations/reports
            await db.execute(
                delete(Evaluation).where(Evaluation.interview_id == interview.interview_id)
            )
            await db.execute(
                delete(Report).where(Report.interview_id == interview.interview_id)
            )
            await db.commit()

            # Run evaluation graph
            from app.services.graphs.evaluation import build_evaluation_graph
            eval_graph = build_evaluation_graph()

            eval_state = await eval_graph.ainvoke({
                "interview_id": str(interview_id),
                "candidate_id": str(candidate.candidate_id),
                "jd_object": jd.parsed_data or {},
                "transcript_history": transcript_history,
                "evaluations": [],
                "average_score": 0.0,
                "pillar_scores": {},
            })

            # Persist evaluations
            for ev in eval_state.get("evaluations", []):
                db_eval = Evaluation(
                    interview_id=interview.interview_id,
                    pillar=ev.get("pillar"),
                    question=ev.get("question"),
                    answer=ev.get("answer"),
                    reference_answer=ev.get("reference_answer"),
                    correctness=ev.get("correctness"),
                    depth=ev.get("depth"),
                    reasoning=ev.get("reasoning"),
                    clarity=ev.get("clarity"),
                    overall_score=ev.get("overall_score"),
                    justification=ev.get("justification"),
                )
                db.add(db_eval)

            candidate.status = CandidateStatus.EVALUATED
            await db.commit()

            # Run reporting graph
            from app.services.graphs.reporting import build_reporting_graph
            report_graph = build_reporting_graph()

            report_state = await report_graph.ainvoke({
                "interview_id": str(interview_id),
                "candidate_id": str(candidate.candidate_id),
                "candidate_name": candidate.name,
                "jd_title": jd.title,
                "jd_object": jd.parsed_data or {},
                "evaluations": eval_state.get("evaluations", []),
                "pillar_scores": eval_state.get("pillar_scores", {}),
                "average_score": eval_state.get("average_score", 0),
                "cheating_flags": state.get("cheating_flags", []),
            })

            # Parse recommendation
            rec_str = str(report_state.get("recommendation", "borderline")).lower()
            try:
                rec_enum = Recommendation(rec_str)
            except ValueError:
                rec_enum = Recommendation.BORDERLINE

            # Persist report
            db_report = Report(
                interview_id=interview.interview_id,
                candidate_name=candidate.name,
                jd_title=jd.title,
                strengths=report_state.get("strengths"),
                weaknesses=report_state.get("weaknesses"),
                cheating_flags=state.get("cheating_flags", []),
                topic_scores=report_state.get("pillar_scores"),
                final_score=report_state.get("final_score"),
                confidence_score=report_state.get("confidence_score"),
                recommendation=rec_enum,
                summary=report_state.get("summary"),
                detailed_feedback=report_state.get("detailed_feedback"),
            )
            db.add(db_report)
            candidate.status = CandidateStatus.REPORTED
            await db.commit()

            logger.info(f"Post-interview analysis complete for {interview_id}")

    except Exception as e:
        logger.error(f"Post-interview analysis failed for {interview_id}: {e}", exc_info=True)


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
