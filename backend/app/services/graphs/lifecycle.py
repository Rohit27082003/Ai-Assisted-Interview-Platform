import asyncio
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.models import (
    Candidate, Interview, JobDescription,
    InterviewStatus, CandidateStatus,
    Evaluation, Report, Recommendation
)
from app.schemas.state import create_initial_state
from app.services.realtime.session_manager import active_sessions, pending_cleanups
from app.services.realtime.interview_broadcaster import (
    get_broadcaster,
    InterviewEventType
)

logger = get_logger(__name__)
settings = get_settings()

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
    
    # Check for "stuck" state on resume (in progress but awaiting answer)
    elif interview.status == InterviewStatus.IN_PROGRESS and interview.state_json:
        state = interview.state_json
        # If we are resuming, we can't be awaiting an answer from a previous dead connection
        if state.get("awaiting_answer"):
            logger.warning(f"Resuming interview {interview.interview_id} with stuck 'awaiting_answer'. Clearing flag.")
            state["awaiting_answer"] = False

            # Check if we need to clean up timing that might have expired
            timing = state.get("timing", {})
            now = datetime.now(timezone.utc)

            if timing.get("answer_deadline"):
                try:
                    deadline = datetime.fromisoformat(timing["answer_deadline"].replace("Z", "+00:00"))
                    if now > deadline:
                        logger.warning(f"Answer deadline expired for {interview.interview_id}, marking question as timed out")
                        # Mark the current question as timed out
                        question_records = state.get("question_records", [])
                        if question_records and not question_records[-1].get("answer_text"):
                            question_records[-1]["answer_text"] = "[TIMEOUT - Session disconnected]"
                            state["question_records"] = question_records
                except Exception as e:
                    logger.error(f"Error checking deadline: {e}")

            # Reset phase to allow graph to continue
            if state.get("phase") in ["awaiting_answer", "answering", "reading"]:
                state["phase"] = "questioning"
                logger.info(f"Reset phase to 'questioning' for {interview.interview_id}")

            interview.state_json = state

async def run_post_interview_analysis(interview_id: str):
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

async def handle_disconnect_cleanup(interview_id: str, broadcaster):
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
                asyncio.create_task(run_post_interview_analysis(interview_id))

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
            await handle_disconnect_cleanup(interview_id, broadcaster)
        else:
            logger.info(f"User reconnected for {interview_id}, skipping cleanup")
    except asyncio.CancelledError:
        logger.info(f"Cleanup cancelled for interview {interview_id} - user reconnected")
    finally:
        pending_cleanups.pop(interview_id, None)
