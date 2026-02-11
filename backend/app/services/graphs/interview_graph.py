"""
Interview Orchestration Graph - Production Implementation

This module implements the minimal production interview loop:

ENTRY → pillar_manager → question_engine → [interrupt: await_audio] →
        audio_pipeline → answer_analyzer → decision_router → LOOP/END

Key Principles:
1. Single InterviewState schema persisted in PostgreSQL JSONB
2. All transitions are state-based (no direct node branching)
3. Only decision_router can terminate the interview
4. Structured LLM outputs (no manual parsing)
5. Server-side timing enforcement
6. Full observability via transition logging
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.state import (
    InterviewState,
    InterviewPhase,
    RouterDecision,
    create_initial_state,
)
from app.services.graphs.nodes import (
    pillar_manager_node,
    question_engine_node,
    audio_pipeline_node,
    answer_analyzer_node,
)
from app.services.graphs.routers import make_routing_decision

logger = get_logger(__name__)
settings = get_settings()


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════════


def build_interview_graph(checkpointer: Optional[AsyncPostgresSaver] = None) -> StateGraph:
    """
    Build the interview orchestration graph.

    The graph implements a state machine with the following flow:
    1. pillar_manager: Initializes/transitions pillars
    2. question_engine: Generates questions
    3. [INTERRUPT]: Waits for candidate audio input
    4. audio_pipeline: Processes the answer
    5. answer_analyzer: Produces evaluation signals
    6. decision_router: Makes routing decision (only component that can end)
    7. Loop back or terminate based on router decision

    Args:
        checkpointer: PostgreSQL checkpointer for state persistence

    Returns:
        Compiled StateGraph ready for execution
    """

    # Create the graph with interview state
    graph = StateGraph(InterviewState)

    # ─── Add Nodes ────────────────────────────────────────────────────────────

    graph.add_node("pillar_manager", _pillar_manager_wrapper)
    graph.add_node("question_engine", _question_engine_wrapper)
    graph.add_node("audio_pipeline", _audio_pipeline_wrapper)
    graph.add_node("answer_analyzer", _answer_analyzer_wrapper)
    graph.add_node("decision_router", _decision_router_wrapper)

    # ─── Define Edges ─────────────────────────────────────────────────────────

    # Entry point
    graph.set_entry_point("pillar_manager")

    # pillar_manager -> question_engine (or END if interview ending)
    graph.add_conditional_edges(
        "pillar_manager",
        _route_from_pillar_manager,
        {
            "question_engine": "question_engine",
            "end": END,
        },
    )

    # question_engine -> audio_pipeline (interrupt happens here)
    graph.add_edge("question_engine", "audio_pipeline")

    # audio_pipeline -> answer_analyzer
    graph.add_edge("audio_pipeline", "answer_analyzer")

    # answer_analyzer -> decision_router
    graph.add_edge("answer_analyzer", "decision_router")

    # decision_router -> conditional routing
    graph.add_conditional_edges(
        "decision_router",
        _route_from_decision_router,
        {
            "pillar_manager": "pillar_manager",
            "question_engine": "question_engine",
            "end": END,
        },
    )

    # ─── Compile with Checkpointer ────────────────────────────────────────────

    compiled = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["audio_pipeline"],  # Pause for candidate input
    )

    logger.info("Interview graph compiled successfully")
    return compiled


# ═══════════════════════════════════════════════════════════════════════════════
# NODE WRAPPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _create_node_wrapper(node_func, node_name: str):
    """Factory to create error-handling wrappers for graph nodes."""
    async def wrapper(state: InterviewState) -> Dict[str, Any]:
        try:
            return await node_func(state)
        except Exception as e:
            logger.error(f"{node_name} error: {e}", exc_info=True)
            return {
                "error_count": state.get("error_count", 0) + 1,
                "last_error": str(e),
            }
    wrapper.__name__ = f"_{node_name}_wrapper"
    return wrapper


_pillar_manager_wrapper = _create_node_wrapper(pillar_manager_node, "Pillar manager")
_question_engine_wrapper = _create_node_wrapper(question_engine_node, "Question engine")


async def _audio_pipeline_wrapper(state: InterviewState) -> Dict[str, Any]:
    """
    Wrapper for audio_pipeline_node.

    This node is special - it's where the graph interrupts to wait
    for candidate input. The answer_text and audio_url are injected
    when the graph is resumed.
    """
    # The actual input is provided during graph resume via state update
    answer_text = state.get("_injected_answer_text")
    audio_url = state.get("_injected_audio_url")

    if answer_text is None:
        # Graph is being interrupted here - waiting for input
        logger.debug("Audio pipeline waiting for input (interrupt point)")
        return {"awaiting_answer": True}

    try:
        result = await audio_pipeline_node(state, answer_text, audio_url)
        # Clear injected values
        result["_injected_answer_text"] = None
        result["_injected_audio_url"] = None
        return result
    except Exception as e:
        logger.error(f"Audio pipeline error: {e}", exc_info=True)
        return {
            "error_count": state.get("error_count", 0) + 1,
            "last_error": str(e),
            "_injected_answer_text": None,
            "_injected_audio_url": None,
        }


async def _answer_analyzer_wrapper(state: InterviewState) -> Dict[str, Any]:
    """Wrapper for answer_analyzer_node with error handling and fallback signals."""
    try:
        return await answer_analyzer_node(state)
    except Exception as e:
        logger.error(f"Answer analyzer error: {e}", exc_info=True)
        return {
            "error_count": state.get("error_count", 0) + 1,
            "last_error": str(e),
            "last_analysis_signals": {
                "overall_signal_score": 5.0,
                "has_probeable_gaps": False,
            },
        }


async def _decision_router_wrapper(state: InterviewState) -> Dict[str, Any]:
    """
    Wrapper for decision router.

    This is the ONLY place that can determine interview termination.
    """
    try:
        decision, updated_state = make_routing_decision(state)

        # Return only the updates (state already has base values)
        return {
            "router_decision": updated_state.get("router_decision"),
            "phase": updated_state.get("phase"),
            "termination_conditions": updated_state.get("termination_conditions"),
            "transition_log": updated_state.get("transition_log"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Decision router error: {e}", exc_info=True)
        # On error, continue safely
        return {
            "router_decision": RouterDecision.CONTINUE_PILLAR.value,
            "error_count": state.get("error_count", 0) + 1,
            "last_error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _route_from_pillar_manager(state: InterviewState) -> Literal["question_engine", "end"]:
    """Route from pillar_manager based on interview phase."""
    phase = state.get("phase", InterviewPhase.QUESTIONING.value)

    if phase in [InterviewPhase.COMPLETED.value, InterviewPhase.TERMINATED.value]:
        logger.info(f"Interview ending from pillar_manager: phase={phase}")
        return "end"

    return "question_engine"


def _route_from_decision_router(
    state: InterviewState,
) -> Literal["pillar_manager", "question_engine", "end"]:
    """Route from decision_router based on router decision."""
    decision = state.get("router_decision", RouterDecision.CONTINUE_PILLAR.value)

    # Termination decisions
    if decision in [
        RouterDecision.END_COMPLETE.value,
        RouterDecision.END_VIOLATION.value,
        RouterDecision.END_TIMEOUT.value,
        RouterDecision.END_RECRUITER.value,
    ]:
        logger.info(f"Interview ending: decision={decision}")
        return "end"

    # Pillar transition
    if decision == RouterDecision.NEXT_PILLAR.value:
        return "pillar_manager"

    # Continue or follow-up in current pillar
    return "question_engine"


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH EXECUTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

