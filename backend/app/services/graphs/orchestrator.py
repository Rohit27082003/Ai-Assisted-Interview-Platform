"""Master Orchestrator Router.

Routes execution into the correct subgraph based on candidate state.
This is the central decision engine of the platform.

Routing logic:
  if resumes_uploaded → run shortlist
  if shortlisted → run focus
  if focus_done → start interview
  if interviewed → run evaluation
  if evaluated → generate report
"""

from typing import TypedDict, Optional, Dict, Any, List
from langgraph.graph import StateGraph, END

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Orchestrator State ────────────────────────────────────────────

class OrchestratorState(TypedDict):
    candidate_id: str
    jd_id: str
    current_status: str  # maps to CandidateStatus enum
    jd_object: Optional[dict]
    resume_text: Optional[str]
    focus_areas: Optional[List[Dict[str, str]]]
    interview_id: Optional[str]
    next_graph: str  # which graph to trigger
    result: Optional[Dict[str, Any]]
    error: Optional[str]


# ── Router Decision Node ─────────────────────────────────────────

async def router_node(state: OrchestratorState) -> OrchestratorState:
    """Decide which graph to execute next based on candidate status."""
    status = state.get("current_status", "")

    routing_map = {
        "uploaded": "resume_intelligence",
        "parsed": "resume_intelligence",
        "shortlisted": "focus_area",
        "focus_ready": "interview",
        "interviewing": "interview",
        "interviewed": "evaluation",
        "evaluated": "reporting",
        "reported": "complete",
        "rejected": "complete",
    }

    next_graph = routing_map.get(status, "unknown")
    state["next_graph"] = next_graph

    logger.info(
        f"Orchestrator routing: candidate={state['candidate_id']}, "
        f"status={status} → graph={next_graph}"
    )
    return state


async def jd_intelligence_executor(state: OrchestratorState) -> OrchestratorState:
    """Execute JD Intelligence Graph."""
    from app.services.graphs.jd_intelligence import build_jd_intelligence_graph

    graph = build_jd_intelligence_graph()
    result = await graph.ainvoke({
        "raw_text": state.get("jd_object", {}).get("raw_text", ""),
        "title": state.get("jd_object", {}).get("title", ""),
        "parsed_role": "",
        "must_have_skills": [],
        "good_to_have": [],
        "experience_range": "",
        "tools": [],
        "competencies": [],
        "jd_object": {},
    })
    state["jd_object"] = result.get("jd_object", {})
    state["result"] = {"graph": "jd_intelligence", "output": result.get("jd_object")}
    return state


async def resume_intelligence_executor(state: OrchestratorState) -> OrchestratorState:
    """Execute Resume Intelligence Graph."""
    from app.services.graphs.resume_intelligence import build_resume_intelligence_graph

    if not state.get("resume_text") or not state.get("jd_object"):
        state["error"] = "Missing resume_text or jd_object for resume intelligence"
        return state

    graph = build_resume_intelligence_graph()
    result = await graph.ainvoke({
        "candidate_id": state["candidate_id"],
        "jd_id": state["jd_id"],
        "resume_text": state["resume_text"],
        "jd_object": state["jd_object"],
        "chunks": [],
        "chunk_metadata": [],
        "skills_score": 0.0,
        "projects_score": 0.0,
        "experience_score": 0.0,
        "tooling_score": 0.0,
        "final_score": 0.0,
        "recommended": False,
        "scoring_details": {},
    })
    state["result"] = {
        "graph": "resume_intelligence",
        "score": result.get("final_score", 0),
        "recommended": result.get("recommended", False),
        "scoring_details": result.get("scoring_details", {}),
    }
    return state


async def focus_area_executor(state: OrchestratorState) -> OrchestratorState:
    """Execute Focus Area Selection Graph."""
    from app.services.graphs.focus_area import build_focus_area_graph

    if not state.get("jd_object") or not state.get("resume_text"):
        state["error"] = "Missing jd_object or resume_text for focus area selection"
        return state

    graph = build_focus_area_graph()
    result = await graph.ainvoke({
        "candidate_id": state["candidate_id"],
        "jd_object": state["jd_object"],
        "resume_text": state["resume_text"],
        "resume_metadata": {},
        "focus_areas": [],
        "reasoning_trace": "",
    })
    state["focus_areas"] = result.get("focus_areas", [])
    state["result"] = {
        "graph": "focus_area",
        "focus_areas": state["focus_areas"],
    }
    return state


async def evaluation_executor(state: OrchestratorState) -> OrchestratorState:
    """Execute Evaluation Graph."""
    state["result"] = {"graph": "evaluation", "status": "triggered"}
    return state


async def reporting_executor(state: OrchestratorState) -> OrchestratorState:
    """Execute Reporting Graph."""
    state["result"] = {"graph": "reporting", "status": "triggered"}
    return state


async def complete_node(state: OrchestratorState) -> OrchestratorState:
    """Pipeline complete."""
    state["result"] = {"graph": "complete", "status": "pipeline_finished"}
    logger.info(f"Pipeline complete for candidate {state['candidate_id']}")
    return state


async def error_node(state: OrchestratorState) -> OrchestratorState:
    """Handle unknown or error states."""
    state["error"] = state.get("error") or f"Unknown status: {state.get('current_status')}"
    logger.error(f"Orchestrator error: {state['error']}")
    return state


# ── Routing Function ──────────────────────────────────────────────

def route_to_graph(state: OrchestratorState) -> str:
    """Route to the appropriate executor node."""
    next_graph = state.get("next_graph", "unknown")
    valid = {
        "jd_intelligence", "resume_intelligence", "focus_area",
        "interview", "evaluation", "reporting", "complete",
    }
    if next_graph in valid:
        return next_graph
    return "error"


# ── Build Graph ───────────────────────────────────────────────────

def build_orchestrator_graph() -> StateGraph:
    """Build the Master Orchestration Router graph."""
    graph = StateGraph(OrchestratorState)

    graph.add_node("router", router_node)
    graph.add_node("jd_intelligence", jd_intelligence_executor)
    graph.add_node("resume_intelligence", resume_intelligence_executor)
    graph.add_node("focus_area", focus_area_executor)
    graph.add_node("interview", lambda s: s)  # Interview is handled via WebSocket
    graph.add_node("evaluation", evaluation_executor)
    graph.add_node("reporting", reporting_executor)
    graph.add_node("complete", complete_node)
    graph.add_node("error", error_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        route_to_graph,
        {
            "jd_intelligence": "jd_intelligence",
            "resume_intelligence": "resume_intelligence",
            "focus_area": "focus_area",
            "interview": "interview",
            "evaluation": "evaluation",
            "reporting": "reporting",
            "complete": "complete",
            "error": "error",
        },
    )

    # All executors end after running
    for node in ["jd_intelligence", "resume_intelligence", "focus_area",
                  "interview", "evaluation", "reporting", "complete", "error"]:
        graph.add_edge(node, END)

    return graph.compile()
