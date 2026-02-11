import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import UUID
import base64

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.core.config import get_settings
from app.models.models import Interview, Transcript, InterviewStatus
from app.schemas.state import InterviewPhase, RouterDecision, CheatingLevel
from app.services.graphs.nodes.answer_analyzer import CHEATING_THRESHOLDS
from app.utils.datetime_helpers import parse_iso_datetime
from app.services.realtime.interview_broadcaster import (
    InterviewEventType,
    create_question_asked_event,
    create_answer_analyzed_event,
    create_cheating_flag_event,
    create_pillar_completed_event,
    create_interview_completed_event,
)
from app.services.realtime.session_manager import active_sessions, get_session
from app.services.aws.s3_service import get_s3_service
from app.services.graphs.lifecycle import run_post_interview_analysis
from app.services.realtime.timer_service import get_or_create_timer, stop_timer
from app.utils.serialization import serialize_state

logger = get_logger(__name__)
settings = get_settings()

async def run_graph_cycle(
    graph,
    config: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    broadcaster,
):
    """Run a graph execution cycle and handle events.

    LangGraph's astream() naturally stops yielding when it hits an
    interrupt_before node (audio_pipeline). No manual aget_state check
    is needed — the async-for loop simply ends at the interrupt point.
    """
    try:
        logger.info(f"Starting graph cycle for {interview_id}")
        async for event in graph.astream(None, config, stream_mode="updates"):
            await handle_graph_event(
                event, websocket, interview_id, broadcaster
            )

        # Log where the graph paused after the stream ends
        state_snap = await graph.aget_state(config)
        if state_snap and state_snap.next:
            logger.info(f"Graph paused at interrupt for {interview_id}. Next: {state_snap.next}")
        else:
            logger.info(f"Graph cycle fully completed for {interview_id}")

    except Exception as e:
        logger.error(f"Graph cycle error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"Graph error: {str(e)}"}
        })

async def handle_graph_event(
    event: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    broadcaster,
):
    """Process events emitted by the graph nodes."""
    for node_name, state_update in event.items():
        # astream can yield interrupt metadata (tuples) — skip non-dict events
        if not isinstance(state_update, dict):
            logger.debug(f"Skipping non-dict event for {node_name}: {type(state_update).__name__}")
            continue

        logger.info(f"GRAPH EVENT [{interview_id}]: Node={node_name}, Keys={list(state_update.keys())}")

        if "error" in state_update:
            logger.error(f"Node {node_name} reported error: {state_update.get('last_error')}")

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

                # Start reading phase timer
                timer = get_or_create_timer(interview_id, websocket)
                await timer.start_reading_phase()

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
                # Check for "No answer provided" (silence/timeout)
                if signals.get("analysis_summary") == "No answer provided":
                    await websocket.send_json({
                        "type": "warning",
                        "data": {"message": "No answer detected. Moving to next question."}
                    })

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

            # Check for pending warning message (mid-interview cheating warning to candidate)
            warning_message = state_update.get("_pending_warning_message")
            if warning_message:
                await websocket.send_json({
                    "type": "cheating_warning",
                    "data": {
                        "message": warning_message,
                        "level": state_update.get("cheating_level", "none"),
                        "cumulative_score": state_update.get("cheating_score", 0),
                    }
                })
                logger.warning(f"Sent cheating warning to candidate {interview_id}: {warning_message}")

            # Check for cheating flags (broadcast to recruiters)
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
                        # Merge router update into the full persisted state
                        full_state = dict(interview.state_json or {})
                        full_state.update(serialize_state(state_update))
                        interview.state_json = full_state
                        await db.commit()

                # Broadcast completion
                timing = state_update.get("timing", {})
                started_at = timing.get("interview_started_at")
                duration = 0
                if started_at:
                    start = parse_iso_datetime(started_at)
                    duration = (datetime.now(timezone.utc) - start).total_seconds() / 60

                await broadcaster.broadcast(
                    interview_id,
                    InterviewEventType.INTERVIEW_COMPLETED,
                    create_interview_completed_event(
                        completion_status=decision,
                        total_questions=state_update.get("total_questions_asked", 0),
                        total_pillars=state_update.get("total_pillars", 0),
                        duration_minutes=duration,
                        final_score=None,
                    ),
                )
                
                # Trigger post-interview analysis
                asyncio.create_task(run_post_interview_analysis(interview_id))

async def handle_answer_complete(
    graph,
    config: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    data: Dict[str, Any],
    transcribe_service,
    broadcaster,
):
    """Handle completed answer submission."""
    # Stop timer
    await stop_timer(interview_id)

    stream_id = f"stream-{interview_id}"

    # Get final transcription
    logger.info(f"Stopping transcription stream for {interview_id}")
    final_text = await transcribe_service.stop_stream(stream_id) or ""
    user_text = data.get("text", "")
    final_answer = user_text or final_text or "(No answer provided)"

    logger.info(f"Answer received for {interview_id}: {len(final_answer)} chars")

    # Upload audio to S3 if raw audio bytes were sent
    audio_url = data.get("audio_url")  # Pre-uploaded URL from frontend
    audio_base64 = data.get("audio_data")  # Raw audio bytes (base64)
    if not audio_url and audio_base64:
        try:
            
            audio_bytes = base64.b64decode(audio_base64)
            state_snap = await graph.aget_state(config)
            q_num = state_snap.values.get("total_questions_asked", 0) if state_snap and state_snap.values else 0
            s3 = get_s3_service()
            audio_url = await s3.upload_audio(audio_bytes, interview_id, q_num)
            logger.info(f"Uploaded answer audio to S3: {audio_url}")
        except Exception as e:
            logger.error(f"Failed to upload audio to S3: {e}", exc_info=True)
            # Continue without audio URL — don't block the interview

    # Update state with answer - CRITICAL: Include the injected keys
    await graph.aupdate_state(config, {
        "_injected_answer_text": final_answer,
        "_injected_audio_url": audio_url,
    })

    # Resume graph (audio_pipeline → answer_analyzer → decision_router)
    await run_graph_cycle(graph, config, websocket, interview_id, broadcaster)

    # Sync state to DB
    state_snap = await graph.aget_state(config)
    if state_snap and state_snap.values:
        async with async_session_factory() as db:
            interview = await db.get(Interview, UUID(interview_id))
            if interview:
                interview.state_json = serialize_state(dict(state_snap.values))
                
                # Persist Transcript
                question_records = state_snap.values.get("question_records", [])
                if question_records:
                    last = question_records[-1]
                    # Check if transcript already exists
                    existing_transcript = await db.execute(
                        select(Transcript).where(
                            Transcript.interview_id == interview.interview_id,
                            Transcript.question == last.get("question_text") 
                        )
                    )
                    if not existing_transcript.scalars().first():
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

async def handle_violation(
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
            "severity": 7.0,
        })

        cheating_score = state.get("cheating_score", 0) + 3.0
        cheating_level = state.get("cheating_level", "none")

        if cheating_score >= CHEATING_THRESHOLDS["penalty"]:
            cheating_level = CheatingLevel.PENALTY.value
        elif cheating_score >= CHEATING_THRESHOLDS["warning_2"]:
            cheating_level = CheatingLevel.WARNING_2.value
        elif cheating_score >= CHEATING_THRESHOLDS["warning_1"]:
            cheating_level = CheatingLevel.WARNING_1.value

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

async def handle_answer_started(graph, config: Dict[str, Any], interview_id: str, websocket=None):
    """Handle when candidate starts answering (updates timing and starts answering timer)."""
    now = datetime.now(timezone.utc)
    state_snap = await graph.aget_state(config)
    if state_snap and state_snap.values:
        timing = state_snap.values.get("timing", {})
        timing["answer_started_at"] = now.isoformat()
        await graph.aupdate_state(config, {"timing": timing})

    # Start answering phase timer
    timer = get_or_create_timer(interview_id, websocket)
    await timer.start_answering_phase()

async def handle_request_finish(
    websocket: WebSocket,
    interview_id: str,
    broadcaster,
):
    """Handle candidate request to finish interview early."""
    logger.info(f"Candidate requested finish for {interview_id}")

    # Stop any running timer
    await stop_timer(interview_id)

    # Update DB status
    async with async_session_factory() as db:
        interview = await db.get(Interview, UUID(interview_id))
        if interview:
            interview.status = InterviewStatus.COMPLETED
            interview.ended_at = datetime.now(timezone.utc)
            # Mark reason in state
            state = dict(interview.state_json or {})
            state["phase"] = InterviewPhase.COMPLETED.value
            state["router_decision"] = "user_completed"
            interview.state_json = state
            await db.commit()

    # Trigger post-interview analysis
    asyncio.create_task(run_post_interview_analysis(interview_id))

    # Broadcast completion to recruiters
    await broadcaster.broadcast(
        interview_id,
        InterviewEventType.INTERVIEW_COMPLETED,
        create_interview_completed_event(
            completion_status="user_completed",
            total_questions=0,
            total_pillars=0,
            duration_minutes=0,
            final_score=None,
        ),
    )

    # Send completion message to candidate
    await websocket.send_json({
        "type": "complete",
        "data": {
            "message": "Interview completed by user request",
            "reason": "user_completed",
        }
    })


async def run_interview_event_loop(
    graph,
    config: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    transcribe_service,
    broadcaster,
):
    """
    Shared WebSocket event loop for interview sessions.

    Handles all message types: start, audio_chunk, answer_started,
    answer_complete, violation, request_finish, and ping.

    Used by both recruiter and candidate WebSocket endpoints.
    """
    import base64
    import json

    # Define transcript callbacks once (reused for all audio chunks)
    async def on_partial(text):
        try:
            if interview_id in active_sessions:
                await websocket.send_json({
                    "type": "transcript_partial",
                    "data": {"text": text}
                })
        except Exception as e:
            logger.error(f"Failed to send partial transcript: {e}")

    async def on_final(text):
        try:
            if interview_id in active_sessions:
                await websocket.send_json({
                    "type": "transcript_final",
                    "data": {"text": text}
                })
        except Exception as e:
            logger.error(f"Failed to send final transcript: {e}")

    while True:
        # Check for termination flag
        session = get_session(interview_id) or {}
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

        logger.info(f"WS MESSAGE [{interview_id}]: type={msg_type}")

        if msg_type == "start":
            await run_graph_cycle(graph, config, websocket, interview_id, broadcaster)

        elif msg_type == "audio_chunk":
            chunk_data = msg.get("data", {})
            audio_bytes = base64.b64decode(chunk_data.get("chunk", ""))
            stream_id = f"stream-{interview_id}"

            # Start stream if not active
            if not transcribe_service.is_active(stream_id):
                # Detect audio format from frontend (ogg-opus or webm-opus)
                mime_type = chunk_data.get("mime_type", "")
                media_format = "ogg-opus"
                if "webm" in mime_type:
                    media_format = "webm-opus"

                await transcribe_service.start_stream(
                    interview_id,
                    on_partial=on_partial,
                    on_final=on_final,
                    media_format=media_format,
                )

            await transcribe_service.feed_audio(stream_id, audio_bytes)

        elif msg_type == "answer_started":
            await handle_answer_started(graph, config, interview_id, websocket)

        elif msg_type == "answer_complete":
            logger.info(f"Processing answer_complete for {interview_id}")
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
