"""Graph 6 — Reporting Graph.

Generates recruiter-grade output including:
  - strengths, weaknesses
  - cheating flags
  - topic scores
  - recommendation (hire / no-hire / borderline)
  - confidence score
"""

from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

from app.prompts import (
    PERFORMANCE_ANALYSIS_PROMPT,
    HIRING_RECOMMENDATION_PROMPT,
)

from app.core.llm import get_llm, get_structured_llm
from app.schemas.outputs.reporting_outputs import PerformanceAnalysisOutput, HiringRecommendationOutput
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Graph State ───────────────────────────────────────────────────

class ReportGraphState(TypedDict):
    interview_id: str
    candidate_id: str
    candidate_name: str
    candidate_email: str
    jd_title: str
    jd_object: dict
    evaluations: List[Dict[str, Any]]
    pillar_scores: Dict[str, float]
    average_score: float
    cheating_flags: List[Dict[str, Any]]
    strengths: List[str]
    weaknesses: List[str]
    recommendation: str
    confidence_score: float
    summary: str
    detailed_feedback: Dict[str, Any]
    final_score: float
    focus_areas: List[Dict[str, Any]]
    total_questions_asked: int
    interview_duration_minutes: float
    hitl_database_key: str
    transcript_summary: List[Dict[str, Any]]


# ── Node Functions ────────────────────────────────────────────────

async def analyze_performance_node(state: ReportGraphState) -> ReportGraphState:
    """Analyze interview performance to identify strengths and weaknesses."""
    llm = get_structured_llm(PerformanceAnalysisOutput)

    # Build evaluation summary
    eval_summary = ""
    for ev in state.get("evaluations", []):
        eval_summary += (
            f"Topic: {ev.get('pillar', 'N/A')}\n"
            f"Q: {ev.get('question', '')}\n"
            f"Score: {ev.get('overall_score', 0)}/5\n"
            f"Correctness: {ev.get('correctness', 0)}, Depth: {ev.get('depth', 0)}, "
            f"Reasoning: {ev.get('reasoning', 0)}, Clarity: {ev.get('clarity', 0)}, "
            f"Relevance: {ev.get('relevance', 0)}, Practical: {ev.get('practical_application', 0)}\n"
            f"Justification: {ev.get('justification', '')}\n"
            f"Comparison: {ev.get('expected_vs_actual_comparison', '')}\n\n"
        )

    # Build prompt inputs
    prompt_inputs = {
        "job_role": state.get("jd_title", "Candidate"),
        "job_requirements": "Standard requirements for this role", # Placeholder as it's not in state
        "pillar_scores": str(state.get("pillar_scores", {})),
        "evaluations_json": eval_summary,
        "cheating_flags": str(state.get("cheating_flags", [])),
    }

    chain = PERFORMANCE_ANALYSIS_PROMPT | llm
    
    try:
        response: PerformanceAnalysisOutput = await chain.ainvoke(prompt_inputs)
        # Store as simple strings for compatibility with frontend/state expectation
        state["strengths"] = [f"{s.area}: {s.observation}" for s in response.strengths]
        state["weaknesses"] = [f"{w.area}: {w.observation}" for w in response.weaknesses]
    except Exception as e:
        logger.error(f"Performance analysis failed: {e}")
        state["strengths"] = []
        state["weaknesses"] = []

    logger.info(f"Performance analyzed for interview {state['interview_id']}")
    return state


async def generate_recommendation_node(state: ReportGraphState) -> ReportGraphState:
    """Generate hire/no-hire/borderline recommendation with confidence score."""
    llm = get_structured_llm(HiringRecommendationOutput, temperature=0.1)

    cheating_summary = ""
    if state.get("cheating_flags"):
        cheating_summary = f"Cheating flags detected: {len(state['cheating_flags'])} incidents. "
        for flag in state["cheating_flags"]:
            cheating_summary += f"Level: {flag.get('level', 'unknown')}, Reasons: {flag.get('reasons', [])}. "

    # Build performance analysis summary for the prompt
    performance_analysis = (
        f"Strengths: {', '.join(state.get('strengths', []))}\n"
        f"Weaknesses: {', '.join(state.get('weaknesses', []))}"
    )

    prompt_inputs = {
        "job_role": state.get("jd_title", "Candidate"),
        "job_requirements": "Standard requirements",
        "overall_score": str(state.get("average_score", 0)),
        "performance_analysis": performance_analysis,
        "cheating_assessment": cheating_summary or "Clean",
        "team_context": "General hiring context",
    }

    chain = HIRING_RECOMMENDATION_PROMPT | llm
    
    try:
        response: HiringRecommendationOutput = await chain.ainvoke(prompt_inputs)
        state["recommendation"] = response.recommendation
        state["confidence_score"] = response.confidence
        # Handle summary mapping - ensure default handles empty logic if model has optional
        state["summary"] = response.summary or f"{response.recommendation.replace('_', ' ').title()} - {response.role_fit_rationale}"
        
    except Exception as e:
        logger.error(f"Recommendation generation failed: {e}")
        # Fallback based on score
        avg = state.get("average_score", 0)
        has_penalty = any(
            f.get("level") == "penalty" for f in state.get("cheating_flags", [])
        )
        if has_penalty or avg < 3.0:
            state["recommendation"] = "no_hire"
        elif avg >= 4.0:
            state["recommendation"] = "hire"
        else:
            state["recommendation"] = "borderline"
        state["confidence_score"] = 0.5
        state["summary"] = "Automated recommendation based on scores (fallback)."

    state["final_score"] = state.get("average_score", 0)
    logger.info(
        f"Recommendation for interview {state['interview_id']}: "
        f"{state['recommendation']} (confidence={state['confidence_score']})"
    )
    return state


async def compile_report_node(state: ReportGraphState) -> ReportGraphState:
    """Compile the full comprehensive report with HITL database key."""
    import uuid
    from datetime import datetime, timezone

    # Generate unique HITL (Human-In-The-Loop) database key for answer retrieval
    hitl_key = f"HITL-{state.get('candidate_id', '')[:8]}-{state.get('interview_id', '')[:8]}-{uuid.uuid4().hex[:8]}"
    state["hitl_database_key"] = hitl_key

    # Build transcript summary
    transcript_summary = []
    for ev in state.get("evaluations", []):
        transcript_summary.append({
            "pillar": ev.get("pillar", ""),
            "question": ev.get("question", ""),
            "answer": ev.get("answer", ""),
            "is_follow_up": ev.get("is_follow_up", False),
            "score": ev.get("overall_score", 0),
        })

    state["transcript_summary"] = transcript_summary

    # Compile detailed feedback with comprehensive information
    state["detailed_feedback"] = {
        # Candidate Information
        "candidate_details": {
            "candidate_id": state.get("candidate_id", ""),
            "candidate_name": state.get("candidate_name", ""),
            "candidate_email": state.get("candidate_email", ""),
            "interview_id": state.get("interview_id", ""),
            "job_title": state.get("jd_title", ""),
            "interview_duration_minutes": state.get("interview_duration_minutes", 0),
            "total_questions_asked": state.get("total_questions_asked", 0),
            "hitl_database_key": hitl_key,
            "report_generated_at": datetime.now(timezone.utc).isoformat(),
        },

        # Focus Areas/Topics Covered
        "focus_areas_covered": state.get("focus_areas", []),

        # Overall Performance
        "performance_summary": {
            "final_score": state.get("final_score", 0),
            "average_score": state.get("average_score", 0),
            "pillar_scores": state.get("pillar_scores", {}),
            "recommendation": state.get("recommendation", ""),
            "confidence": state.get("confidence_score", 0),
            "summary": state.get("summary", ""),
        },

        # Strengths and Weaknesses
        "analysis": {
            "strengths": state.get("strengths", []),
            "weaknesses": state.get("weaknesses", []),
        },

        # Per-Question Evaluation
        "per_question_evaluation": [
            {
                "question_number": idx + 1,
                "pillar": ev.get("pillar", ""),
                "question": ev.get("question", ""),
                "answer": ev.get("answer", "")[:200] + "..." if len(ev.get("answer", "")) > 200 else ev.get("answer", ""),
                "is_follow_up": ev.get("is_follow_up", False),
                "scores": {
                    "correctness": ev.get("correctness", 0),
                    "depth": ev.get("depth", 0),
                    "reasoning": ev.get("reasoning", 0),
                    "clarity": ev.get("clarity", 0),
                    "relevance": ev.get("relevance", 0),
                    "practical_application": ev.get("practical_application", 0),
                    "overall": ev.get("overall_score", 0),
                },
                "justification": ev.get("justification", ""),
                "expected_vs_actual_comparison": ev.get("expected_vs_actual_comparison", ""),
                "similarity_score": ev.get("similarity_score", 0.0),
                "cheating_flagged": ev.get("cheating_flagged", False),
                "cheating_penalty": ev.get("cheating_penalty", 0.0),
            }
            for idx, ev in enumerate(state.get("evaluations", []))
        ],

        # Cheating/Integrity Analysis
        "integrity_analysis": {
            "total_flags": len(state.get("cheating_flags", [])),
            "has_violations": len(state.get("cheating_flags", [])) > 0,
            "flags_detail": state.get("cheating_flags", []),
            "integrity_status": "clean" if len(state.get("cheating_flags", [])) == 0
                              else "warning" if len(state.get("cheating_flags", [])) <= 2
                              else "serious_concern",
        },

        # Recruiter Decision Support
        "recruiter_insights": {
            "hire_recommendation": state.get("recommendation", ""),
            "confidence_level": state.get("confidence_score", 0),
            "key_strengths": state.get("strengths", [])[:3],  # Top 3
            "key_concerns": state.get("weaknesses", [])[:3],  # Top 3
            "fitment_score": state.get("final_score", 0),
            "decision_factors": [
                f"Average performance: {state.get('average_score', 0):.1f}/5",
                f"Questions answered: {state.get('total_questions_asked', 0)}",
                f"Integrity flags: {len(state.get('cheating_flags', []))}",
            ],
        },
    }

    logger.info(f"Comprehensive report compiled for interview {state['interview_id']} with HITL key: {hitl_key}")
    return state


# ── Build Graph ───────────────────────────────────────────────────

def build_reporting_graph() -> StateGraph:
    """Build and compile the Reporting Graph."""
    graph = StateGraph(ReportGraphState)

    graph.add_node("analyze_performance", analyze_performance_node)
    graph.add_node("generate_recommendation", generate_recommendation_node)
    graph.add_node("compile_report", compile_report_node)

    graph.set_entry_point("analyze_performance")
    graph.add_edge("analyze_performance", "generate_recommendation")
    graph.add_edge("generate_recommendation", "compile_report")
    graph.add_edge("compile_report", END)

    return graph.compile()
