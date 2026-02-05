"""API routes for Interview management, including WebSocket for live interviews."""

import asyncio
import json
import base64
from uuid import UUID
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db, async_session_factory
from app.models.models import (
    Candidate, Interview, Transcript, JobDescription,
    InterviewStatus, CandidateStatus, CheatingLevel,
)
from app.schemas.schemas import InterviewStartRequest, InterviewResponse, InterviewProgress
from app.services.graphs.interview_orchestration import build_interview_graph
from app.services.agents.cheating_detection import get_cheating_detector
from app.services.aws.transcribe_service import get_transcribe_service
from app.services.aws.s3_service import get_s3_service
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/interviews", tags=["Interviews"])

# Active interview sessions (in-memory; use Redis in production)
active_sessions: Dict[str, Dict[str, Any]] = {}


@router.post("/start", response_model=InterviewResponse)
async def start_interview(
    request: InterviewStartRequest,
    db: AsyncSession = Depends(get_db),
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

    # Create interview record
    interview = Interview(
        candidate_id=request.candidate_id,
        status=InterviewStatus.PENDING,
        state_json={
            "focus_areas": candidate.focus_areas or [],
            "jd_object": jd.parsed_data or {},
        },
        current_pillar=candidate.focus_areas[0]["skill"] if candidate.focus_areas else "General",
    )
    db.add(interview)
    await db.flush()

    # Initialize graph state
    focus_areas = candidate.focus_areas or [{"skill": "General", "reason": "Default"}]
    graph_state = {
        "interview_id": str(interview.interview_id),
        "candidate_id": str(candidate.candidate_id),
        "jd_object": jd.parsed_data or {},
        "resume_text": candidate.resume_text or "",
        "focus_areas": focus_areas,
        "current_pillar_index": 0,
        "current_pillar": focus_areas[0]["skill"],
        "question_number": 0,
        "questions_in_pillar": 0,
        "max_questions_per_pillar": settings.MAX_QUESTIONS_PER_TOPIC,
        "current_question": "",
        "current_answer": "",
        "is_follow_up": False,
        "follow_up_count": 0,
        "transcript_history": [],
        "pillar_complete": False,
        "all_pillars_complete": False,
        "next_action": "generate_question",
        "cheating_flags": [],
    }

    # Store session
    active_sessions[str(interview.interview_id)] = {
        "graph_state": graph_state,
        "candidate_id": str(candidate.candidate_id),
    }

    # Update candidate status
    candidate.status = CandidateStatus.INTERVIEWING

    logger.info(f"Interview started: {interview.interview_id} for candidate {candidate.candidate_id}")
    return interview


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get interview details."""
    interview = await db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.get("/{interview_id}/progress")
async def get_progress(interview_id: UUID):
    """Get current interview progress from active session."""
    session = active_sessions.get(str(interview_id))
    if not session:
        raise HTTPException(status_code=404, detail="No active session for this interview")

    state = session["graph_state"]
    return InterviewProgress(
        interview_id=interview_id,
        candidate_id=UUID(state["candidate_id"]),
        status="in_progress" if not state["all_pillars_complete"] else "completed",
        current_pillar=state.get("current_pillar", ""),
        question_number=state.get("question_number", 0),
        total_questions=sum(
            1 for t in state.get("transcript_history", [])
        ),
        cheating_level=state.get("cheating_flags", [{}])[-1].get("level", "none") if state.get("cheating_flags") else "none",
    )


# ── WebSocket Interview Session ──────────────────────────────────

@router.websocket("/ws/{interview_id}")
async def interview_websocket(websocket: WebSocket, interview_id: str):
    """WebSocket endpoint for live interview streaming.

    Protocol:
      Server → Client messages:
        {"type": "question", "data": {"question_text": "", "pillar": "", ...}}
        {"type": "timer", "data": {"phase": "reading"|"answering", "seconds_left": N}}
        {"type": "cheating_warning", "data": {"level": "", "message": ""}}
        {"type": "complete", "data": {"message": ""}}
        {"type": "error", "data": {"message": ""}}

      Client → Server messages:
        {"type": "start", "data": {}}
        {"type": "audio_chunk", "data": {"chunk": "base64...", "sequence": N}}
        {"type": "answer_text", "data": {"text": ""}}
        {"type": "answer_complete", "data": {}}
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for interview {interview_id}")

    session = active_sessions.get(interview_id)
    if not session:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "No active interview session found"}
        })
        await websocket.close()
        return

    graph_state = session["graph_state"]
    cheating_detector = get_cheating_detector()
    transcribe_service = get_transcribe_service()

    try:
        while True:
            # Receive message from client
            raw_msg = await websocket.receive_text()
            msg = json.loads(raw_msg)
            msg_type = msg.get("type", "")

            if msg_type == "start":
                # Generate first question
                graph = build_interview_graph()
                result = await graph.ainvoke(graph_state)
                graph_state.update(result)
                session["graph_state"] = graph_state

                # Send question to client
                await websocket.send_json({
                    "type": "question",
                    "data": {
                        "question_text": graph_state["current_question"],
                        "pillar": graph_state["current_pillar"],
                        "question_number": graph_state["question_number"],
                        "is_follow_up": graph_state.get("is_follow_up", False),
                        "reading_time_seconds": settings.READING_TIME_SECONDS,
                        "answer_time_seconds": settings.ANSWER_TIME_SECONDS,
                    }
                })

                # Start reading timer
                await _run_timer(websocket, "reading", settings.READING_TIME_SECONDS)

                # Signal answering phase
                await websocket.send_json({
                    "type": "timer",
                    "data": {"phase": "answering", "seconds_left": settings.ANSWER_TIME_SECONDS}
                })

                # Start transcription stream
                stream_id = await transcribe_service.start_stream(interview_id)

                # Schedule auto-close after answer time
                asyncio.create_task(
                    _auto_close_answer(
                        websocket, transcribe_service, stream_id,
                        settings.ANSWER_TIME_SECONDS, interview_id
                    )
                )

            elif msg_type == "audio_chunk":
                # Forward audio to transcription service
                chunk_data = msg.get("data", {})
                audio_bytes = base64.b64decode(chunk_data.get("chunk", ""))
                stream_id = f"stream-{interview_id}"
                await transcribe_service.feed_audio(stream_id, audio_bytes)

                # Optionally upload to S3
                try:
                    s3 = get_s3_service()
                    await s3.upload_audio(audio_bytes, interview_id, chunk_data.get("sequence", 0))
                except Exception:
                    pass

            elif msg_type == "answer_text":
                # Direct text answer (for testing or fallback)
                answer_text = msg.get("data", {}).get("text", "")
                graph_state["current_answer"] = answer_text

            elif msg_type == "answer_complete":
                # Process the answer
                answer_text = (
                    msg.get("data", {}).get("text", "")
                    or graph_state.get("current_answer", "")
                )
                graph_state["current_answer"] = answer_text

                # Stop transcription
                stream_id = f"stream-{interview_id}"
                final_transcript = await transcribe_service.stop_stream(stream_id)
                if final_transcript:
                    graph_state["current_answer"] = final_transcript

                # Run cheating detection in parallel
                cheating_result = await cheating_detector.analyze(
                    question=graph_state["current_question"],
                    answer=graph_state["current_answer"],
                    question_number=graph_state["question_number"],
                    existing_flags=graph_state.get("cheating_flags", []),
                )

                if cheating_result["is_flagged"]:
                    graph_state.setdefault("cheating_flags", []).append(cheating_result)
                    await websocket.send_json({
                        "type": "cheating_warning",
                        "data": {
                            "level": cheating_result["level"],
                            "message": f"Warning: {', '.join(cheating_result['reasons'])}",
                        }
                    })

                # Store transcript in DB
                async with async_session_factory() as db_session:
                    transcript = Transcript(
                        interview_id=UUID(interview_id),
                        pillar=graph_state["current_pillar"],
                        question_number=graph_state["question_number"],
                        question=graph_state["current_question"],
                        answer=graph_state["current_answer"],
                        is_follow_up=graph_state.get("is_follow_up", False),
                        cheating_flag=CheatingLevel(cheating_result["level"]),
                        cheating_details=cheating_result if cheating_result["is_flagged"] else None,
                    )
                    db_session.add(transcript)

                    # Update interview state
                    interview = await db_session.get(Interview, UUID(interview_id))
                    if interview:
                        interview.state_json = graph_state
                        interview.current_pillar = graph_state["current_pillar"]
                        interview.question_number = graph_state["question_number"]
                    await db_session.commit()

                # Run answer understanding through the graph
                from app.services.graphs.interview_orchestration import answer_understanding_node
                graph_state = await answer_understanding_node(graph_state)
                session["graph_state"] = graph_state

                # Check if interview is complete
                if graph_state.get("all_pillars_complete") or graph_state.get("next_action") == "end":
                    # Mark interview as completed
                    async with async_session_factory() as db_session:
                        interview = await db_session.get(Interview, UUID(interview_id))
                        if interview:
                            interview.status = InterviewStatus.COMPLETED
                            interview.ended_at = datetime.now(timezone.utc)
                            interview.state_json = graph_state

                        candidate = await db_session.get(
                            Candidate, UUID(graph_state["candidate_id"])
                        )
                        if candidate:
                            candidate.status = CandidateStatus.INTERVIEWED
                        await db_session.commit()

                    await websocket.send_json({
                        "type": "complete",
                        "data": {"message": "Interview completed. Thank you!"}
                    })
                    break
                else:
                    # Generate next question
                    next_action = graph_state["next_action"]
                    if next_action == "follow_up":
                        from app.services.graphs.interview_orchestration import followup_generator_node
                        graph_state = await followup_generator_node(graph_state)
                    elif next_action == "next_pillar":
                        from app.services.graphs.interview_orchestration import shift_pillar_node, select_pillar_node, generate_question_node
                        graph_state = await shift_pillar_node(graph_state)
                        if not graph_state.get("all_pillars_complete"):
                            graph_state = await select_pillar_node(graph_state)
                            graph_state = await generate_question_node(graph_state)
                    elif next_action == "generate_question":
                        from app.services.graphs.interview_orchestration import generate_question_node
                        graph_state = await generate_question_node(graph_state)

                    session["graph_state"] = graph_state

                    if graph_state.get("all_pillars_complete"):
                        await websocket.send_json({
                            "type": "complete",
                            "data": {"message": "Interview completed. Thank you!"}
                        })
                        break

                    # Send next question
                    await websocket.send_json({
                        "type": "question",
                        "data": {
                            "question_text": graph_state["current_question"],
                            "pillar": graph_state["current_pillar"],
                            "question_number": graph_state["question_number"],
                            "is_follow_up": graph_state.get("is_follow_up", False),
                            "reading_time_seconds": settings.READING_TIME_SECONDS,
                            "answer_time_seconds": settings.ANSWER_TIME_SECONDS,
                        }
                    })

                    # Run timers
                    await _run_timer(websocket, "reading", settings.READING_TIME_SECONDS)
                    await websocket.send_json({
                        "type": "timer",
                        "data": {"phase": "answering", "seconds_left": settings.ANSWER_TIME_SECONDS}
                    })

                    stream_id = await transcribe_service.start_stream(interview_id)
                    asyncio.create_task(
                        _auto_close_answer(
                            websocket, transcribe_service, stream_id,
                            settings.ANSWER_TIME_SECONDS, interview_id
                        )
                    )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for interview {interview_id}")
    except Exception as e:
        logger.error(f"WebSocket error for interview {interview_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e)}
            })
        except Exception:
            pass
    finally:
        # Clean up session
        if interview_id in active_sessions:
            # Persist final state
            async with async_session_factory() as db_session:
                interview = await db_session.get(Interview, UUID(interview_id))
                if interview and interview.status == InterviewStatus.IN_PROGRESS:
                    interview.status = InterviewStatus.COMPLETED
                    interview.ended_at = datetime.now(timezone.utc)
                    interview.state_json = active_sessions[interview_id]["graph_state"]
                await db_session.commit()


async def _run_timer(websocket: WebSocket, phase: str, total_seconds: int):
    """Run a server-side countdown timer, sending updates to the client."""
    for remaining in range(total_seconds, 0, -5):
        await asyncio.sleep(5)
        try:
            await websocket.send_json({
                "type": "timer",
                "data": {"phase": phase, "seconds_left": remaining - 5}
            })
        except Exception:
            break


async def _auto_close_answer(websocket, transcribe_service, stream_id, seconds, interview_id):
    """Auto-close the answer phase after timeout. Server-side timer enforcement."""
    await asyncio.sleep(seconds)
    try:
        await transcribe_service.stop_stream(stream_id)
        await websocket.send_json({
            "type": "timer",
            "data": {"phase": "answering", "seconds_left": 0, "auto_closed": True}
        })
    except Exception:
        pass
