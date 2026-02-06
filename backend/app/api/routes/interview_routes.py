"""API routes for Interview management, including WebSocket for live interviews."""

import asyncio
import json
import base64
from uuid import UUID
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_core.messages import HumanMessage, AIMessage

from app.core.database import get_db, async_session_factory
from app.models.models import (
    Candidate, Interview, Transcript, JobDescription,
    InterviewStatus, CandidateStatus, CheatingLevel,
)
from app.schemas.schemas import InterviewStartRequest, InterviewResponse, InterviewProgress
from app.services.graphs.interview_orchestration import build_interview_graph, get_initial_state, InterviewState
from app.services.graphs.postgres_checkpoint import get_postgres_checkpointer, execution_checkpointer
from app.services.agents.cheating_detection import get_cheating_detector
from app.services.aws.transcribe_service import get_transcribe_service
from app.services.aws.s3_service import get_s3_service
from app.api.middleware.auth_middleware import require_recruiter, AuthenticatedUser
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/interviews", tags=["Interviews"])

# Trigger reload (KeyError fix applied)
# Active interview sessions (Memory cache for WebSockets/Streams)
# We still keep this for ephemeral data not in the graph checkpointer? 
# Actually, checkpointer handles state. session dict handles implementation details (socket, streams).
active_sessions: Dict[str, Dict[str, Any]] = {}


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

    # Get clean initial state
    raw_state = get_initial_state()
    # Populate context
    raw_state.update({
        "interview_id": "", # Will update after DB create
        "candidate_id": str(candidate.candidate_id),
        "job_role": jd.title,
        "resume_context": candidate.resume_text or "",
        "focus_areas": candidate.focus_areas or [],
        "current_pillar_index": -1, # Will be incremented to 0 on first run
    })

    # Create interview record
    interview = Interview(
        candidate_id=request.candidate_id,
        status=InterviewStatus.PENDING,
        state_json=raw_state, # Initial snapshot
        current_pillar="Pending",
    )
    db.add(interview)
    await db.flush()
    
    interview.state_json = raw_state

    logger.info(f"Interview started: {interview.interview_id} for candidate {candidate.candidate_id}")
    return interview


def ensure_active_session(interview: Interview, candidate: Candidate, jd: JobDescription):
    """
    Ensure the interview has a valid initial state in the DB.
    Refactored for new Graph architecture: explicit active_sessions dict population 
    is no longer needed here as it happens on WebSocket connect.
    We just ensure the DB state_json is seeded.
    """
    if interview.state_json and interview.state_json.get("interview_id"):
        return

    # Use the same initialization logic as start_interview
    raw_state = get_initial_state()
    raw_state.update({
        "interview_id": str(interview.interview_id),
        "candidate_id": str(candidate.candidate_id),
        "job_role": jd.title,
        "resume_context": candidate.resume_text or "",
        "focus_areas": candidate.focus_areas or [],
        "current_pillar_index": -1,
    })
    
    interview.state_json = raw_state
    logger.info(f"Ensured initial state for interview {interview.interview_id}")


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get interview details with full transcript."""
    interview = await db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    # We rely on DB state for viewing (snapshot)
    # Checkpointer is the source of truth for "Live", but DB is synced occasionally.
    # For now, let's grab from DB.
        
    state: InterviewState = interview.state_json or {}
    
    # If active, maybe try to fetch latest from checkpointer?
    # For now, simplicity: return DB snapshot. The WS updates DB on completion/steps.
    
    transcript = []
    history = state.get("message_history", [])
    # Convert message history to transcript dicts for frontend
    # This is a basic reconstruction. 
    # Ideal: Store separate structured transcript list in state.
    
    return InterviewResponse(
        interview_id=interview.interview_id,
        candidate_id=interview.candidate_id,
        status=interview.status.value if interview.status else "pending",
        started_at=interview.started_at,
        current_pillar=interview.current_pillar,
        question_number=state.get("question_count_in_pillar", 0),
        transcript=[], # TODO: reconstruct if needed or use stored transcript field
    )


@router.get("/{interview_id}/progress")
async def get_progress(
    interview_id: UUID,
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get current interview progress."""
    async with async_session_factory() as db:
        interview = await db.get(Interview, interview_id)
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        
        state: InterviewState = interview.state_json or {}
        
        # Check active session for "Real-time" status
        is_active = str(interview_id) in active_sessions
        
        return InterviewProgress(
            interview_id=interview_id,
            candidate_id=interview.candidate_id,
            status="in_progress" if is_active else (interview.status.value if interview.status else "pending"),
            current_pillar=state.get("current_pillar", ""),
            question_number=state.get("question_count_in_pillar", 0),
            total_questions=0, # Calc from history
            cheating_level="none", # TODO
        )


@router.get("/monitor/active")
async def get_active_interviews(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Get list of currently active interviews."""
    if not active_sessions:
        return []

    # Get candidate details for active sessions
    # Since active_sessions is keyed by interview_id
    interview_ids = [UUID(k) for k in active_sessions.keys()]
    if not interview_ids:
        return []
        
    result = await db.execute(select(Interview).where(Interview.interview_id.in_(interview_ids)))
    interviews = result.scalars().all()
    
    stats = []
    for interview in interviews:
        cand = await db.get(Candidate, interview.candidate_id)
        state = interview.state_json or {}
        
        stats.append({
            "interview_id": str(interview.interview_id),
            "candidate_name": cand.name if cand else "Unknown",
            "candidate_email": cand.email if cand else "",
            "question_number": state.get("question_count_in_pillar", 0),
            "status": "completed" if state.get("router_decision") == "end" else "in_progress",
        })
    return stats


# ── WebSocket Interview Session ──────────────────────────────────

@router.websocket("/ws/{interview_id}")
async def interview_websocket(websocket: WebSocket, interview_id: str):
    """WebSocket endpoint for live interview streaming with New Graph Architecture."""
    await websocket.accept()
    logger.info(f"WebSocket connected for interview {interview_id}")

    transcribe_service = get_transcribe_service()
    
    # 1. Initialize Checkpointer
    checkpointer = await get_postgres_checkpointer()
    
    # 2. Build Graph
    graph = build_interview_graph(checkpointer=checkpointer)
    
    # Thread config for persistence
    config = {"configurable": {"thread_id": interview_id}}

    # Load initial state from DB if checkpointer is empty?
    # Actually checkpointer persists. But if this is first run, we need to load from DB or Init.
    # We'll check if state exists in checkpointer.

    current_state_snap = await graph.aget_state(config)
    if not current_state_snap.created_at:
        # Load from DB
        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if interview and interview.state_json:
                # Seed the graph state from DB
                # Note: We can't easily seed checkpointer history, but we can update current state
                await graph.aupdate_state(config, interview.state_json)
                logger.info(f"Seeded graph state from DB for {interview_id}")

    # Register session
    active_sessions[interview_id] = {
        "websocket": websocket,
        "terminated": False
    }

    try:
        while True:
            # Check external termination
            if active_sessions.get(interview_id, {}).get("terminated"):
                await websocket.send_json({"type": "error", "data": {"message": "Terminated"}})
                break

            raw_msg = await websocket.receive_text()
            msg = json.loads(raw_msg)
            msg_type = msg.get("type", "")

            if msg_type == "start":
                # Kicks off the graph or Helper to "resume" if already running?
                # "start" implies "Next Step" in our graph entry.
                
                # Check where we are.
                snap = await graph.aget_state(config)
                if not snap.next:
                     # Start logic
                     async for event in graph.astream(None, config):
                         # Handle events (node updates)
                         await _handle_graph_event(websocket, event, interview_id)
                else:
                    # Resume logic (if stuck)
                    async for event in graph.astream(None, config):
                         await _handle_graph_event(websocket, event, interview_id)

            elif msg_type == "audio_chunk":
                chunk_data = msg.get("data", {})
                audio_bytes = base64.b64decode(chunk_data.get("chunk", ""))
                stream_id = f"stream-{interview_id}"
                await transcribe_service.feed_audio(stream_id, audio_bytes)

            elif msg_type == "answer_complete":
                # 1. Stop Transcription
                stream_id = f"stream-{interview_id}"
                final_text = await transcribe_service.stop_stream(stream_id)
                
                user_text = msg.get("data", {}).get("text", "")
                final_answer = user_text or final_text or "(No answer)"
                
                # 2. Update Graph State with Answer
                await graph.aupdate_state(config, {
                    "current_answer_text": final_answer
                })
                
                # 3. Resume Graph (Analysis -> Router -> Next)
                async for event in graph.astream(None, config):
                     await _handle_graph_event(websocket, event, interview_id)

            elif msg_type == "violation":
                 # Log violation in state
                 pass # Implement later

    except WebSocketDisconnect:
        logger.info(f"WS Disconnect: {interview_id}")
    except Exception as e:
        logger.error(f"WS Error {interview_id}: {e}")
    finally:
        active_sessions.pop(interview_id, None)
        
        # Checking for auto-submission requirement
        # If the interview was NOT finished gracefully, we must finish it now.
        # We check the Interview status in DB or local state.
        
        try:
             async with async_session_factory() as db:
                interview = await db.get(Interview, UUID(interview_id))
                if interview and interview.status in (InterviewStatus.PENDING, InterviewStatus.IN_PROGRESS):
                    logger.info(f"Auto-submitting disconnected interview: {interview_id}")
                    interview.status = InterviewStatus.COMPLETED
                    interview.ended_at = datetime.now(timezone.utc)
                    await db.commit()
                    
                    # Trigger analysis in background
                    # Note: BackgroundTasks is preferred, but simple await is okay for now 
                    # as this is a finally block of a task.
                    # Actually, creating a task is better to not block the socket close (though socket is already closed).
                    asyncio.create_task(_run_post_interview_analysis(interview_id))
                    
        except Exception as e:
            logger.error(f"Failed to auto-submit interview {interview_id}: {e}")


async def _handle_graph_event(websocket: WebSocket, event: Dict, interview_id: str):
    """Process graph updates and notify frontend."""
    # event is like: {'question_engine': {'current_question': '...'}}
    
    for node, state_update in event.items():
        if node == "question_engine":
            # New Question Generated
            q_text = state_update.get("current_question")
            
            # Send to frontend
            # We need to update DB with latest snapshot? -> Checkpointer handles it.
            # But the 'Interview' table status needs update maybe.
            
            await websocket.send_json({
                "type": "question",
                "data": {
                    "question_text": q_text,
                    "pillar": "Current Pillar", # Need to fetch from full state if not in diff
                    "question_number": state_update.get("question_count_in_pillar", 0),
                    "reading_time_seconds": settings.READING_TIME_SECONDS,
                    "answer_time_seconds": settings.ANSWER_TIME_SECONDS,
                }
            })
            
            # Auto-start timers? Frontend expects "timer" message?
            # Or frontend handles reading time on receipt of question
            
        elif node == "pillar_manager":
            # Pillar changed?
            # Notify?
            pass
            
        elif node == "decision_router":
            decision = state_update.get("router_decision")
            if decision == "end":
                await websocket.send_json({
                    "type": "complete", 
                    "data": {"message": "Interview Finished"}
                })
                # Update DB status to COMPLETED
                async with async_session_factory() as db:
                    interview = await db.get(Interview, UUID(interview_id))
                    if interview:
                        interview.status = InterviewStatus.COMPLETED
                        interview.ended_at = datetime.now(timezone.utc)
                    await db.commit()



async def _restore_session(interview_id: str) -> Dict[str, Any]:
    """Recover an active session from the database if server restarted."""
    try:
        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if not interview:
                return None

            # Allow recovery if status is pending or in_progress
            if interview.status not in (InterviewStatus.PENDING, InterviewStatus.IN_PROGRESS):
                return None

            # Restore state
            if not interview.state_json:
                return None

            graph_state = interview.state_json

            # Re-populate active_sessions
            session_data = {
                "graph_state": graph_state,
                "candidate_id": str(interview.candidate_id),
            }
            active_sessions[interview_id] = session_data
            logger.info(f"Restored session for interview {interview_id} from DB")
            return session_data
    except Exception as e:
        logger.error(f"Failed to restore session {interview_id}: {e}")
        return None


async def _run_post_interview_analysis(interview_id: str):
    """Run evaluation and reporting graphs in background."""
    logger.info(f"Starting post-interview analysis for {interview_id}")
    
    async with async_session_factory() as db:
        interview = await db.get(Interview, UUID(interview_id))
        if not interview:
            return
            
        candidate = await db.get(Candidate, interview.candidate_id)
        jd = await db.get(JobDescription, candidate.jd_id)
        
        # 1. Run Evaluation
        from app.services.graphs.evaluation import build_evaluation_graph
        eval_graph = build_evaluation_graph()
        
        # Helper to convert SQLA objects to dict (naive)
        transcript_history = interview.state_json.get("transcript_history", [])
        
        # Clean up existing evaluations/reports to allow re-runs
        from app.models.models import Evaluation, Report
        await db.execute(select(Evaluation).where(Evaluation.interview_id == interview.interview_id))
        # Note: Delete isn't directly supported by execute(select), we need delete() statement
        from sqlalchemy import delete
        await db.execute(delete(Evaluation).where(Evaluation.interview_id == interview.interview_id))
        await db.execute(delete(Report).where(Report.interview_id == interview.interview_id))
        await db.commit()
        
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
        for ev in eval_state["evaluations"]:
            from app.models.models import Evaluation
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
        
        # 2. Run Reporting
        from app.services.graphs.reporting import build_reporting_graph
        report_graph = build_reporting_graph()
        
        report_state = await report_graph.ainvoke({
            "interview_id": str(interview_id),
            "candidate_id": str(candidate.candidate_id),
            "candidate_name": candidate.name,
            "jd_title": jd.title,
            "jd_object": jd.parsed_data or {},
            "evaluations": eval_state["evaluations"],
            "pillar_scores": eval_state["pillar_scores"],
            "average_score": eval_state["average_score"],
            "cheating_flags": interview.state_json.get("cheating_flags", []),
        })
        
        # Persist Report
        from app.models.models import Report, Recommendation
        
        # Robust enum casting
        rec_str = str(report_state.get("recommendation", "borderline")).lower()
        try:
            rec_enum = Recommendation(rec_str)
        except ValueError:
            logger.warning(f"Invalid recommendation '{rec_str}', defaulting to BORDERLINE")
            rec_enum = Recommendation.BORDERLINE

        db_report = Report(
            interview_id=interview.interview_id,
            candidate_name=candidate.name,
            jd_title=jd.title,
            strengths=report_state.get("strengths"),
            weaknesses=report_state.get("weaknesses"),
            cheating_flags=interview.state_json.get("cheating_flags", []),
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
