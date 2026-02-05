"""Graph 6 — Reporting Graph.

Generates recruiter-grade output including:
  - strengths, weaknesses
  - cheating flags
  - topic scores
  - recommendation (hire / no-hire / borderline)
  - confidence score
"""

from typing import TypedDict, List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

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

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a senior hiring manager writing a candidate evaluation report.

Role: {jd_title}
Candidate: {candidate_name}
Average Score: {avg_score}/5
Topic Scores: {pillar_scores}

Evaluation Details:
{eval_summary}

Identify:
1. Top 3-5 strengths (specific to the interview performance)
2. Top 3-5 weaknesses or areas of concern
3. Any notable observations

Return ONLY a JSON:
{{
  "strengths": ["list of specific strengths"],
  "weaknesses": ["list of specific weaknesses"],
  "observations": "any notable observations"
}}
Do not include any markdown formatting."""),
        ("human", "Analyze this candidate's performance."),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({
        "jd_title": state.get("jd_title", ""),
        "candidate_name": state.get("candidate_name", ""),
        "avg_score": state.get("average_score", 0),
        "pillar_scores": str(state.get("pillar_scores", {})),
        "eval_summary": eval_summary,
    })

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

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are making a final hiring recommendation.

Role: {jd_title}
Average Score: {avg_score}/5
Strengths: {strengths}
Weaknesses: {weaknesses}
{cheating_info}

Decision criteria:
- Score >= 4.0 and no penalty flags → HIRE
- Score >= 3.0 and score < 4.0 → BORDERLINE (unless penalty flags)
- Score < 3.0 or penalty cheating flags → NO_HIRE

Return ONLY a JSON:
{{
  "recommendation": "hire" or "no_hire" or "borderline",
  "confidence_score": 0.0 to 1.0,
  "summary": "2-3 paragraph recruiter summary explaining the recommendation"
}}
Do not include any markdown formatting."""),
        ("human", "Generate the hiring recommendation."),
    ])

    chain = prompt | llm
    response = await chain.ainvoke({
        "jd_title": state.get("jd_title", ""),
        "avg_score": state.get("average_score", 0),
        "strengths": str(state.get("strengths", [])),
        "weaknesses": str(state.get("weaknesses", [])),
        "cheating_info": cheating_summary or "No cheating flags detected.",
    })

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
