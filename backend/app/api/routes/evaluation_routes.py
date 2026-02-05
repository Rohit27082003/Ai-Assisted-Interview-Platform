"""API routes for post-interview evaluation and report generation."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    Interview, Candidate, Transcript, Evaluation, Report,
    InterviewStatus, CandidateStatus, Recommendation,
)
from app.schemas.schemas import EvaluationResponse, EvaluationItem, ReportResponse
from app.services.graphs.evaluation import build_evaluation_graph
from app.services.graphs.reporting import build_reporting_graph
from app.models.models import JobDescription
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/evaluations", tags=["Evaluations"])


@router.post("/{interview_id}/evaluate", response_model=EvaluationResponse)
async def evaluate_interview(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run evaluation graph on a completed interview."""
    interview = await db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    if interview.status != InterviewStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Interview must be completed before evaluation")

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
            overall_score=ev.get("overall_score", 3.0),
            justification=ev.get("justification", ""),
        )
        db.add(db_eval)

        eval_items.append(EvaluationItem(
            question=ev.get("question", ""),
            answer=ev.get("answer", ""),
            reference_answer=ev.get("reference_answer", ""),
            correctness=ev.get("correctness", 3),
            depth=ev.get("depth", 3),
            reasoning=ev.get("reasoning", 3),
            clarity=ev.get("clarity", 3),
            overall_score=ev.get("overall_score", 3.0),
            justification=ev.get("justification", ""),
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
):
    """Generate a recruiter-grade report for a completed and evaluated interview."""
    interview = await db.get(Interview, interview_id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    candidate = await db.get(Candidate, interview.candidate_id)
    jd = await db.get(JobDescription, candidate.jd_id) if candidate else None

    # Get evaluations
    result = await db.execute(
        select(Evaluation).where(Evaluation.interview_id == interview_id)
    )
    evaluations = result.scalars().all()

    if not evaluations:
        raise HTTPException(status_code=400, detail="No evaluations found. Run evaluation first.")

    # Build evaluation data
    eval_data = [
        {
            "pillar": e.pillar,
            "question": e.question,
            "answer": e.answer,
            "correctness": e.correctness,
            "depth": e.depth,
            "reasoning": e.reasoning,
            "clarity": e.clarity,
            "overall_score": e.overall_score,
            "justification": e.justification,
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

    # Run Reporting Graph
    report_graph = build_reporting_graph()
    report_result = await report_graph.ainvoke({
        "interview_id": str(interview_id),
        "candidate_id": str(interview.candidate_id),
        "candidate_name": candidate.name if candidate else "Unknown",
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
    })

    # Determine recommendation enum
    rec_str = report_result.get("recommendation", "borderline")
    rec_enum = {
        "hire": Recommendation.HIRE,
        "no_hire": Recommendation.NO_HIRE,
        "borderline": Recommendation.BORDERLINE,
    }.get(rec_str, Recommendation.BORDERLINE)

    # Store report in DB
    cheating_flag_strings = []
    for flag in cheating_flags:
        if isinstance(flag, dict):
            cheating_flag_strings.append(
                f"Level: {flag.get('level', 'unknown')}, Reasons: {flag.get('reasons', [])}"
            )

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
        recommendation=rec_str,
        summary=report.summary,
        detailed_feedback=report.detailed_feedback,
        created_at=report.created_at,
    )


@router.get("/{interview_id}/report", response_model=ReportResponse)
async def get_report(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """Retrieve an existing report."""
    result = await db.execute(
        select(Report).where(Report.interview_id == interview_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

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
        detailed_feedback=report.detailed_feedback,
        created_at=report.created_at,
    )
