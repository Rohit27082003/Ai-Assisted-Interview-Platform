"""Graph 3 — Focus Area Selection Graph.

Uses LLM reasoning to select 4-5 focus areas for the interview
based on JD requirements and candidate's resume.
"""

from typing import TypedDict, List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.llm import get_llm
from app.schemas.schemas import FocusArea
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Graph State ───────────────────────────────────────────────────

class FocusAreaGraphState(TypedDict):
    candidate_id: str
    jd_object: dict
    resume_text: str
    resume_metadata: dict
    focus_areas: List[Dict[str, str]]
    reasoning_trace: str


# ── Node Functions ────────────────────────────────────────────────

async def analyze_overlap_node(state: FocusAreaGraphState) -> FocusAreaGraphState:
    """Analyze the overlap between JD requirements and resume to identify probe areas."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a senior technical interviewer preparing for a candidate interview.

Given the Job Description requirements and the candidate's resume, identify exactly 4-5
focus areas that should be deeply probed during the interview.

For each focus area, explain WHY it should be probed:
- Is it a critical JD requirement the candidate claims to have?
- Is it a project they worked on that is highly relevant?
- Is it a gap that needs verification?
- Is it a strength that could differentiate them?

JD Requirements:
- Role: {role}
- Must-have skills: {must_have_skills}
- Tools: {tools}
- Competencies: {competencies}
- Experience needed: {experience_range}

Return ONLY a JSON array of objects with keys "skill" and "reason".
Example: [{{"skill": "Distributed Systems", "reason": "Mentioned in recent project at Company X, core JD requirement"}}]
Limit to exactly 4-5 items. Do not include any markdown formatting."""),
        ("human", "Candidate Resume:\n{resume_text}"),
    ])

    jd = state["jd_object"]
    chain = prompt | llm
    response = await chain.ainvoke({
        "role": jd.get("role", ""),
        "must_have_skills": str(jd.get("must_have_skills", [])),
        "tools": str(jd.get("tools", [])),
        "competencies": str(jd.get("competencies", [])),
        "experience_range": jd.get("experience_range", ""),
        "resume_text": state["resume_text"][:6000],
    })

    import json
    try:
        areas = json.loads(response.content)
        if isinstance(areas, list):
            state["focus_areas"] = areas[:5]
        else:
            state["focus_areas"] = []
    except (json.JSONDecodeError, AttributeError):
        state["focus_areas"] = []

    logger.info(f"Focus areas identified: {len(state['focus_areas'])} for candidate {state['candidate_id']}")
    return state


async def validate_focus_node(state: FocusAreaGraphState) -> FocusAreaGraphState:
    """Validate and refine focus areas to ensure they are interview-worthy."""
    if len(state["focus_areas"]) < 3:
        # Fallback: generate generic focus areas from JD
        llm = get_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Generate 4 technical interview focus areas based on this job description.
Return ONLY a JSON array of objects with "skill" and "reason" keys.
Do not include any markdown formatting."""),
            ("human", "JD: {jd_text}"),
        ])
        chain = prompt | llm
        jd = state["jd_object"]
        response = await chain.ainvoke({
            "jd_text": str(jd),
        })
        import json
        try:
            areas = json.loads(response.content)
            state["focus_areas"] = areas[:5]
        except (json.JSONDecodeError, AttributeError):
            # Last resort fallback
            skills = state["jd_object"].get("must_have_skills", [])
            state["focus_areas"] = [
                {"skill": s, "reason": "Core JD requirement"} for s in skills[:4]
            ]

    state["reasoning_trace"] = f"Selected {len(state['focus_areas'])} focus areas"
    logger.info(f"Focus areas validated for candidate {state['candidate_id']}")
    return state


# ── Build Graph ───────────────────────────────────────────────────

def build_focus_area_graph() -> StateGraph:
    """Build and compile the Focus Area Selection Graph."""
    graph = StateGraph(FocusAreaGraphState)

    graph.add_node("analyze_overlap", analyze_overlap_node)
    graph.add_node("validate_focus", validate_focus_node)

    graph.set_entry_point("analyze_overlap")
    graph.add_edge("analyze_overlap", "validate_focus")
    graph.add_edge("validate_focus", END)

    return graph.compile()
