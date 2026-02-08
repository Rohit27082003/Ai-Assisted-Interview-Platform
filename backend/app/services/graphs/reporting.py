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

from app.core.llm import get_llm
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Graph State ───────────────────────────────────────────────────

class ReportGraphState(TypedDict):
    interview_id: str
    candidate_id: str
    candidate_name: str
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


# ── Node Functions ────────────────────────────────────────────────

async def analyze_performance_node(state: ReportGraphState) -> ReportGraphState:
    """Analyze interview performance to identify strengths and weaknesses."""
    llm = get_llm()

    # Build evaluation summary
    eval_summary = ""
    for ev in state.get("evaluations", []):
        eval_summary += (
            f"Topic: {ev.get('pillar', 'N/A')}\n"
            f"Q: {ev.get('question', '')}\n"
            f"Score: {ev.get('overall_score', 0)}/5\n"
            f"Correctness: {ev.get('correctness', 0)}, Depth: {ev.get('depth', 0)}, "
            f"Reasoning: {ev.get('reasoning', 0)}, Clarity: {ev.get('clarity', 0)}\n"
            f"Justification: {ev.get('justification', '')}\n\n"
        )

    # Build prompt inputs
    prompt_inputs = {
        "job_role": state.get("jd_title", "Candidate"),
        "job_requirements": "Standard requirements for this role", # Placeholder as it's not in state
        "pillar_scores": str(state.get("pillar_scores", {})),
        "evaluations_json": eval_summary,
        "cheating_flags": str(state.get("cheating_flags", [])),
    }

    response = await PERFORMANCE_ANALYSIS_PROMPT.ainvoke(prompt_inputs)

    import json
    try:
        analysis = json.loads(response.content)
        state["strengths"] = analysis.get("strengths", [])
        state["weaknesses"] = analysis.get("weaknesses", [])
    except (json.JSONDecodeError, AttributeError):
        state["strengths"] = []
        state["weaknesses"] = []

    logger.info(f"Performance analyzed for interview {state['interview_id']}")
    return state


async def generate_recommendation_node(state: ReportGraphState) -> ReportGraphState:
    """Generate hire/no-hire/borderline recommendation with confidence score."""
    llm = get_llm(temperature=0.1)

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

    response = await HIRING_RECOMMENDATION_PROMPT.ainvoke(prompt_inputs)

    import json
    try:
        rec = json.loads(response.content)
        state["recommendation"] = rec.get("recommendation", "borderline")
        state["confidence_score"] = float(rec.get("confidence_score", 0.5))
        state["summary"] = rec.get("summary", "")
    except (json.JSONDecodeError, AttributeError, ValueError):
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
        state["summary"] = "Automated recommendation based on scores."

    state["final_score"] = state.get("average_score", 0)
    logger.info(
        f"Recommendation for interview {state['interview_id']}: "
        f"{state['recommendation']} (confidence={state['confidence_score']})"
    )
    return state


async def compile_report_node(state: ReportGraphState) -> ReportGraphState:
    """Compile the full detailed report."""
    state["detailed_feedback"] = {
        "pillar_scores": state.get("pillar_scores", {}),
        "per_question": [
            {
                "pillar": ev.get("pillar", ""),
                "question": ev.get("question", ""),
                "correctness": ev.get("correctness", 0),
                "depth": ev.get("depth", 0),
                "reasoning": ev.get("reasoning", 0),
                "clarity": ev.get("clarity", 0),
                "overall": ev.get("overall_score", 0),
                "justification": ev.get("justification", ""),
            }
            for ev in state.get("evaluations", [])
        ],
        "cheating_analysis": {
            "total_flags": len(state.get("cheating_flags", [])),
            "flags": state.get("cheating_flags", []),
        },
    }
    logger.info(f"Report compiled for interview {state['interview_id']}")
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
