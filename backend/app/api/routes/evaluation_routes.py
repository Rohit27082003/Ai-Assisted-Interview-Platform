"""API routes for post-interview evaluation and report generation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    Candidate, Transcript, Evaluation, Report,
    InterviewStatus, CandidateStatus, Recommendation,
)
from app.schemas.schemas import EvaluationResponse, EvaluationItem, ReportResponse
from app.services.graphs.evaluation import build_evaluation_graph
from app.services.graphs.reporting import build_reporting_graph
from app.models.models import JobDescription
from app.api.middleware.auth_middleware import require_recruiter, AuthenticatedUser
from app.api.utils.db_utils import verify_interview_ownership, verify_report_ownership
from app.services.aws.s3_service import get_s3_service
from app.core.logging import get_logger

logger = get_logger(__name__)


def _presign_audio_url(url: str | None) -> str | None:
    """Convert an s3:// URI to a presigned HTTPS URL for browser playback."""
    if not url or not url.startswith("s3://"):
        return url
    try:
        return get_s3_service().generate_presigned_url(url, expiration=3600)
    except Exception as e:
        logger.warning(f"Failed to presign audio URL {url}: {e}")
        return None
router = APIRouter(prefix="/api/evaluations", tags=["Evaluations"])


@router.post("/{interview_id}/evaluate", response_model=EvaluationResponse)
async def evaluate_interview(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Run evaluation graph on a completed interview."""
    interview = await verify_interview_ownership(db, interview_id, user.recruiter_id)

    if interview.status not in (InterviewStatus.COMPLETED, InterviewStatus.TERMINATED):
        raise HTTPException(status_code=400, detail="Interview must be completed or terminated before evaluation")

    candidate = await db.get(Candidate, interview.candidate_id)
    jd = await db.get(JobDescription, candidate.jd_id) if candidate else None

    # Get all transcripts
    result = await db.execute(
        select(Transcript)
        .where(Transcript.interview_id == interview_id)
        .order_by(Transcript.question_number)
    )
    transcripts = result.scalars().all()

    if not transcripts:
        raise HTTPException(status_code=404, detail="No transcripts found for this interview")

    # Build transcript history
    transcript_history = [
        {
            "pillar": t.pillar,
            "question": t.question,
            "answer": t.answer or "",
            "is_follow_up": t.is_follow_up,
        }
        for t in transcripts
    ]

    # Collect cheating flags from interview state
    cheating_flags = interview.state_json.get("cheating_flags", []) if interview.state_json else []

    # Run Evaluation Graph
    eval_graph = build_evaluation_graph()
    eval_result = await eval_graph.ainvoke({
        "interview_id": str(interview_id),
        "candidate_id": str(interview.candidate_id),
        "jd_object": jd.parsed_data if jd else {},
        "transcript_history": transcript_history,
        "evaluations": [],
        "average_score": 0.0,
        "pillar_scores": {},
        "cheating_flags": cheating_flags,
    })

    # Store evaluations in DB
    eval_items = []
    for ev in eval_result.get("evaluations", []):
        # Find matching transcript
        matching_transcript = next(
            (t for t in transcripts if t.question == ev.get("question")),
            None,
        )

        db_eval = Evaluation(
            interview_id=interview_id,
            transcript_id=matching_transcript.transcript_id if matching_transcript else None,
            pillar=ev.get("pillar", ""),
            question=ev.get("question", ""),
            answer=ev.get("answer", ""),
            reference_answer=ev.get("reference_answer", ""),
            correctness=ev.get("correctness", 3),
            depth=ev.get("depth", 3),
            reasoning=ev.get("reasoning", 3),
            clarity=ev.get("clarity", 3),
            relevance=ev.get("relevance", 3),
            practical_application=ev.get("practical_application", 3),
            overall_score=ev.get("overall_score", 3.0),
            justification=ev.get("justification", ""),
            expected_vs_actual_comparison=ev.get("expected_vs_actual_comparison", ""),
            similarity_score=ev.get("similarity_score", 0.0),
        )
        db.add(db_eval)

        eval_items.append(EvaluationItem(
            pillar=ev.get("pillar", ""),
            question=ev.get("question", ""),
            answer=ev.get("answer", ""),
            reference_answer=ev.get("reference_answer", ""),
            correctness=ev.get("correctness", 3),
            depth=ev.get("depth", 3),
            reasoning=ev.get("reasoning", 3),
            clarity=ev.get("clarity", 3),
            relevance=ev.get("relevance", 3),
            practical_application=ev.get("practical_application", 3),
            overall_score=ev.get("overall_score", 3.0),
            justification=ev.get("justification", ""),
            expected_vs_actual_comparison=ev.get("expected_vs_actual_comparison", ""),
            similarity_score=ev.get("similarity_score", 0.0),
            audio_url=_presign_audio_url(matching_transcript.audio_url) if matching_transcript else None,
        ))

    # Update candidate status
    if candidate:
        candidate.status = CandidateStatus.EVALUATED

    logger.info(
        f"Evaluation complete for interview {interview_id}: "
        f"avg_score={eval_result.get('average_score', 0)}"
    )

    return EvaluationResponse(
        interview_id=interview_id,
        evaluations=eval_items,
        average_score=eval_result.get("average_score", 0),
    )


@router.post("/{interview_id}/report", response_model=ReportResponse)
async def generate_report(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Generate a recruiter-grade report for a completed and evaluated interview."""
    interview = await verify_interview_ownership(db, interview_id, user.recruiter_id)

    candidate = await db.get(Candidate, interview.candidate_id)
    jd = await db.get(JobDescription, candidate.jd_id) if candidate else None

    # Get evaluations
    result = await db.execute(
        select(Evaluation).where(Evaluation.interview_id == interview_id)
    )
    evaluations = result.scalars().all()

    if not evaluations:
        raise HTTPException(status_code=400, detail="No evaluations found. Run evaluation first.")

    # Fetch transcripts for audio URLs
    transcript_result = await db.execute(
        select(Transcript)
        .where(Transcript.interview_id == interview_id)
        .order_by(Transcript.question_number)
    )
    transcripts = transcript_result.scalars().all()
    transcript_audio_map = {t.question: t.audio_url for t in transcripts}

    # Build evaluation data
    eval_data = [
        {
            "pillar": e.pillar,
            "question": e.question,
            "answer": e.answer,
            "reference_answer": e.reference_answer or "",
            "correctness": e.correctness,
            "depth": e.depth,
            "reasoning": e.reasoning,
            "clarity": e.clarity,
            "relevance": e.relevance or 0,
            "practical_application": e.practical_application or 0,
            "overall_score": e.overall_score,
            "justification": e.justification,
            "expected_vs_actual_comparison": e.expected_vs_actual_comparison or "",
            "similarity_score": e.similarity_score or 0.0,
            "audio_url": _presign_audio_url(transcript_audio_map.get(e.question)),
        }
        for e in evaluations
    ]

    # Compute pillar scores
    pillar_scores = {}
    for e in evaluations:
        pillar_scores.setdefault(e.pillar, []).append(e.overall_score)
    pillar_avg = {
        p: round(sum(scores) / len(scores), 2)
        for p, scores in pillar_scores.items()
    }
    overall_avg = round(
        sum(e.overall_score for e in evaluations) / len(evaluations), 2
    ) if evaluations else 0.0

    # Collect cheating flags from interview state
    cheating_flags = interview.state_json.get("cheating_flags", []) if interview.state_json else []

    # Calculate interview duration
    interview_duration = 0.0
    if interview.started_at and interview.ended_at:
        interview_duration = round(
            (interview.ended_at - interview.started_at).total_seconds() / 60.0, 1
        )

    # Get focus areas and question count from candidate/interview
    focus_areas = candidate.focus_areas if candidate and candidate.focus_areas else []
    total_questions = interview.total_questions or len(evaluations)

    # Run Reporting Graph
    report_graph = build_reporting_graph()
    report_result = await report_graph.ainvoke({
        "interview_id": str(interview_id),
        "candidate_id": str(interview.candidate_id),
        "candidate_name": candidate.name if candidate else "Unknown",
        "candidate_email": candidate.email if candidate else "",
        "jd_title": jd.title if jd else "Unknown",
        "jd_object": jd.parsed_data if jd else {},
        "evaluations": eval_data,
        "pillar_scores": pillar_avg,
        "average_score": overall_avg,
        "cheating_flags": cheating_flags,
        "strengths": [],
        "weaknesses": [],
        "recommendation": "borderline",
        "confidence_score": 0.5,
        "summary": "",
        "detailed_feedback": {},
        "final_score": overall_avg,
        "focus_areas": focus_areas,
        "total_questions_asked": total_questions,
        "interview_duration_minutes": interview_duration,
        "hitl_database_key": "",
        "transcript_summary": [],
    })

    # Determine recommendation enum
    rec_str = report_result.get("recommendation", "borderline")
    rec_enum = {
        "strong_hire": Recommendation.HIRE,
        "hire": Recommendation.HIRE,
        "borderline": Recommendation.BORDERLINE,
        "no_hire": Recommendation.NO_HIRE,
        "strong_no_hire": Recommendation.NO_HIRE,
    }.get(rec_str, Recommendation.BORDERLINE)

    # Store report in DB
    cheating_flag_strings = []
    for flag in cheating_flags:
        if isinstance(flag, dict):
            severity = flag.get("severity", 0)
            level = "High" if severity >= 7 else "Medium" if severity >= 4 else "Low"
            reason = flag.get("reason", "Suspicious behavior detected")
            patterns = flag.get("details", {}).get("pattern_flags", [])
            parts = [f"{level} severity: {reason}"]
            if patterns:
                parts.append(f"Indicators: {', '.join(patterns)}")
            cheating_flag_strings.append(" | ".join(parts))

    report = Report(
        interview_id=interview_id,
        candidate_name=candidate.name if candidate else "Unknown",
        jd_title=jd.title if jd else "Unknown",
        strengths=report_result.get("strengths", []),
        weaknesses=report_result.get("weaknesses", []),
        cheating_flags=cheating_flag_strings,
        topic_scores=pillar_avg,
        final_score=report_result.get("final_score", overall_avg),
        confidence_score=report_result.get("confidence_score", 0.5),
        recommendation=rec_enum,
        summary=report_result.get("summary", ""),
        detailed_feedback=report_result.get("detailed_feedback", {}),
    )
    db.add(report)
    await db.flush()

    # Update candidate status
    if candidate:
        candidate.status = CandidateStatus.REPORTED

    logger.info(
        f"Report generated for interview {interview_id}: "
        f"recommendation={rec_str}"
    )

    # Normalize recommendation string to the 3-value set the frontend expects
    normalized_rec = rec_enum.value  # "hire", "no_hire", or "borderline"

    return ReportResponse(
        report_id=report.report_id,
        interview_id=interview_id,
        candidate_name=report.candidate_name,
        jd_title=report.jd_title,
        strengths=report.strengths,
        weaknesses=report.weaknesses,
        cheating_flags=report.cheating_flags,
        topic_scores=report.topic_scores,
        final_score=report.final_score,
        confidence_score=report.confidence_score,
        recommendation=normalized_rec,
        summary=report.summary,
        detailed_feedback=report.detailed_feedback,
        created_at=report.created_at,
    )


@router.get("/{interview_id}/report", response_model=ReportResponse)
async def get_report(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_recruiter),
):
    """Retrieve an existing report."""
    report = await verify_report_ownership(db, interview_id, user.recruiter_id)

    # Ensure audio URLs are browser-accessible presigned HTTPS URLs
    detailed_feedback = report.detailed_feedback or {}
    per_q_eval = detailed_feedback.get("per_question_evaluation", [])
    if per_q_eval:
        # Fetch transcript audio URLs as fallback for entries missing audio_url
        transcript_result = await db.execute(
            select(Transcript)
            .where(Transcript.interview_id == interview_id)
            .order_by(Transcript.question_number)
        )
        transcripts = transcript_result.scalars().all()
        audio_map = {t.question: t.audio_url for t in transcripts if t.audio_url}

        for ev in per_q_eval:
            url = ev.get("audio_url") or audio_map.get(ev.get("question", ""))
            ev["audio_url"] = _presign_audio_url(url) if url else None
        detailed_feedback = {**detailed_feedback, "per_question_evaluation": per_q_eval}

    return ReportResponse(
        report_id=report.report_id,
        interview_id=report.interview_id,
        candidate_name=report.candidate_name,
        jd_title=report.jd_title,
        strengths=report.strengths,
        weaknesses=report.weaknesses,
        cheating_flags=report.cheating_flags,
        topic_scores=report.topic_scores,
        final_score=report.final_score,
        confidence_score=report.confidence_score,
        recommendation=report.recommendation.value,
        summary=report.summary,
        detailed_feedback=detailed_feedback,
        created_at=report.created_at,
    )
