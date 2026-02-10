"""Graph 3 — Focus Area Selection Graph.

Uses LLM reasoning to select 4-5 focus areas for the interview
based on JD requirements and candidate's resume.
"""

from typing import TypedDict, List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.llm import get_llm, get_structured_llm
from app.schemas.schemas import FocusArea
from app.schemas.outputs.focus_area_outputs import FocusAreaListOutput
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
    from app.prompts.focus_area_prompts import FOCUS_AREA_ANALYSIS_PROMPT
    llm = get_structured_llm(FocusAreaListOutput)
    
    jd = state["jd_object"]
    chain = FOCUS_AREA_ANALYSIS_PROMPT | llm
    
    try:
        response: FocusAreaListOutput = await chain.ainvoke({
            "role": jd.get("role", ""),
            "must_have_skills": str(jd.get("must_have_skills", [])),
            "tools": str(jd.get("tools", [])),
            "competencies": str(jd.get("competencies", [])),
            "experience_range": jd.get("experience_range", ""),
            "resume_text": state["resume_text"][:6000],
        })
        
        # Convert Pydantic models to dicts for state
        state["focus_areas"] = [fa.model_dump() for fa in response.focus_areas]
    except Exception as e:
        logger.error(f"Failed to generate focus areas: {e}")
        state["focus_areas"] = []

    logger.info(f"Focus areas identified: {len(state['focus_areas'])} for candidate {state['candidate_id']}")
    return state


async def validate_focus_node(state: FocusAreaGraphState) -> FocusAreaGraphState:
    """Validate and refine focus areas to ensure they are interview-worthy."""
    if len(state["focus_areas"]) < 3:
        # Fallback: generate generic focus areas from JD
        from app.prompts.focus_area_prompts import FOCUS_AREA_FALLBACK_PROMPT
        llm = get_structured_llm(FocusAreaListOutput)
        chain = FOCUS_AREA_FALLBACK_PROMPT | llm
        jd = state["jd_object"]
        
        try:
            response: FocusAreaListOutput = await chain.ainvoke({
                "jd_text": str(jd),
            })
            state["focus_areas"] = [fa.model_dump() for fa in response.focus_areas][:5]
        except Exception as e:
            logger.error(f"Fallback focus generation failed: {e}")
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
