import asyncio
import base64
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.core.config import get_settings
from app.models.models import Interview, Transcript, InterviewStatus
from app.schemas.state import InterviewPhase, RouterDecision
from app.services.realtime.interview_broadcaster import (
    InterviewEventType,
    create_question_asked_event,
    create_answer_analyzed_event,
    create_cheating_flag_event,
    create_pillar_completed_event,
    create_interview_completed_event,
)
from app.services.realtime.session_manager import active_sessions, pending_cleanups
from app.services.graphs.lifecycle import run_post_interview_analysis

logger = get_logger(__name__)
settings = get_settings()

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

async def run_graph_cycle(
    graph,
    config: Dict[str, Any],
    websocket: WebSocket,
    interview_id: str,
    broadcaster,
):
    """Run a graph execution cycle and handle events."""
    try:
        logger.info(f"Starting graph cycle for {interview_id}")
        async for event in graph.astream(None, config, stream_mode="updates"):
            await handle_graph_event(
                event, websocket, interview_id, broadcaster
            )

            # Check if we hit an interrupt point
            state_snap = await graph.aget_state(config)
            if state_snap and state_snap.next:
                # Only pause if we hit the explicit interrupt point (audio_pipeline)
                if "audio_pipeline" in state_snap.next:
                    logger.debug(f"Graph execution paused (interrupt) for {interview_id}. Next: {state_snap.next}")
                    break
                else:
                    logger.debug(f"Graph continuing... Next: {state_snap.next}")

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
    session = active_sessions.get(interview_id, {})
    stream_id = session.get("stream_id", f"stream-{interview_id}")

    # Get final transcription
    logger.info(f"Stopping transcription stream for {interview_id}")
    final_text = await transcribe_service.stop_stream(stream_id) or ""
    user_text = data.get("text", "")
    final_answer = user_text or final_text or "(No answer provided)"
    
    logger.info(f"Answer received for {interview_id}: {len(final_answer)} chars")

    # Get audio URL if we stored it
    audio_url = data.get("audio_url")

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

async def handle_answer_started(graph, config: Dict[str, Any], interview_id: str):
    """Handle when candidate starts answering (updates timing)."""
    now = datetime.now(timezone.utc)
    state_snap = await graph.aget_state(config)
    if state_snap and state_snap.values:
        timing = state_snap.values.get("timing", {})
        timing["answer_started_at"] = now.isoformat()
        await graph.aupdate_state(config, {"timing": timing})

async def handle_request_finish(
    websocket: WebSocket,
    interview_id: str,
    broadcaster,
):
    """Handle candidate request to finish interview early."""
    logger.info(f"Candidate requested finish for {interview_id}")
    
    # Update DB status
    async with async_session_factory() as db:
        interview = await db.get(Interview, UUID(interview_id))
        if interview:
            interview.status = InterviewStatus.COMPLETED
            interview.ended_at = datetime.now(timezone.utc)
            await db.commit()

    # Trigger post-interview analysis
    asyncio.create_task(run_post_interview_analysis(interview_id))
    
    # Send completion message
    await websocket.send_json({
        "type": "complete",
        "data": {
            "message": "Interview completed by user request",
            "reason": "user_completed",
        }
    })
