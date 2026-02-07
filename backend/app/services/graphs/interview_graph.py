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

import asyncio
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
    log_transition,
)
from app.services.graphs.nodes import (
    pillar_manager_node,
    question_engine_node,
    audio_pipeline_node,
    answer_analyzer_node,
)
from app.services.graphs.routers import (
    DecisionRouter,
    RouterConfig,
    make_routing_decision,
)

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


async def _pillar_manager_wrapper(state: InterviewState) -> Dict[str, Any]:
    """Wrapper for pillar_manager_node with error handling."""
    try:
        return await pillar_manager_node(state)
    except Exception as e:
        logger.error(f"Pillar manager error: {e}", exc_info=True)
        return {
            "error_count": state.get("error_count", 0) + 1,
            "last_error": str(e),
        }


async def _question_engine_wrapper(state: InterviewState) -> Dict[str, Any]:
    """Wrapper for question_engine_node with error handling."""
    try:
        return await question_engine_node(state)
    except Exception as e:
        logger.error(f"Question engine error: {e}", exc_info=True)
        return {
            "error_count": state.get("error_count", 0) + 1,
            "last_error": str(e),
        }


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
    """Wrapper for answer_analyzer_node with error handling."""
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
            "updated_at": datetime.utcnow().isoformat(),
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


async def create_interview_session(
    interview_id: str,
    candidate_id: str,
    jd_id: str,
    candidate_name: str,
    candidate_email: str,
    job_role: str,
    job_requirements: Dict[str, Any],
    resume_context: str,
    focus_areas: list[Dict[str, str]],
    config: Optional[Dict[str, Any]] = None,
    checkpointer: Optional[AsyncPostgresSaver] = None,
) -> InterviewState:
    """
    Create a new interview session with initialized state.

    Args:
        interview_id: UUID of the interview
        candidate_id: UUID of the candidate
        jd_id: UUID of the job description
        candidate_name: Candidate's name
        candidate_email: Candidate's email
        job_role: Title of the job
        job_requirements: Parsed JD requirements
        resume_context: Extracted resume text
        focus_areas: List of focus area dicts
        config: Optional configuration overrides
        checkpointer: Checkpointer for persistence

    Returns:
        Initialized InterviewState
    """
    state = create_initial_state(
        interview_id=interview_id,
        candidate_id=candidate_id,
        jd_id=jd_id,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        job_role=job_role,
        job_requirements=job_requirements,
        resume_context=resume_context,
        focus_areas=focus_areas,
        config=config,
    )

    logger.info(
        f"Created interview session: interview_id={interview_id}, "
        f"candidate={candidate_name}, pillars={len(focus_areas)}"
    )

    return state


async def resume_with_answer(
    graph: StateGraph,
    thread_id: str,
    answer_text: str,
    audio_url: Optional[str] = None,
    checkpointer: Optional[AsyncPostgresSaver] = None,
) -> Dict[str, Any]:
    """
    Resume the graph with candidate's answer.

    This is called after the graph has been interrupted at audio_pipeline.

    Args:
        graph: The compiled interview graph
        thread_id: Thread ID for state lookup
        answer_text: Transcribed answer text
        audio_url: Optional S3 URL for audio
        checkpointer: Checkpointer for state lookup

    Returns:
        Updated state after processing
    """
    config = {"configurable": {"thread_id": thread_id}}

    # Inject the answer into state
    state_update = {
        "_injected_answer_text": answer_text,
        "_injected_audio_url": audio_url,
    }

    logger.info(f"Resuming graph with answer: thread={thread_id}, length={len(answer_text)}")

    # Resume the graph
    result = await graph.ainvoke(state_update, config)

    return result


async def request_termination(
    graph: StateGraph,
    thread_id: str,
    reason: str,
    termination_type: str = "recruiter",
    checkpointer: Optional[AsyncPostgresSaver] = None,
) -> Dict[str, Any]:
    """
    Request interview termination.

    This updates the termination conditions which the router will process.

    Args:
        graph: The compiled interview graph
        thread_id: Thread ID for state lookup
        reason: Reason for termination
        termination_type: Type of termination
        checkpointer: Checkpointer for state lookup

    Returns:
        Updated state
    """
    config = {"configurable": {"thread_id": thread_id}}

    # Get current state
    state = await graph.aget_state(config)
    current_values = state.values if state else {}

    # Update termination conditions
    term_conditions = current_values.get("termination_conditions", {}).copy()

    if termination_type == "recruiter":
        term_conditions["recruiter_terminated"] = True
        term_conditions["recruiter_termination_reason"] = reason
    elif termination_type == "violation":
        term_conditions["hard_violation_detected"] = True
        term_conditions["violation_reason"] = reason
    elif termination_type == "timeout":
        term_conditions["interview_timeout"] = True

    state_update = {"termination_conditions": term_conditions}

    logger.info(f"Termination requested: thread={thread_id}, type={termination_type}")

    # If graph is waiting for input, we need to inject a dummy answer to proceed
    if current_values.get("awaiting_answer"):
        state_update["_injected_answer_text"] = "[TERMINATED BY RECRUITER]"

    result = await graph.ainvoke(state_update, config)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON GRAPH INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════


_graph_instance: Optional[StateGraph] = None


async def get_interview_graph(
    checkpointer: Optional[AsyncPostgresSaver] = None,
) -> StateGraph:
    """Get or create the interview graph instance."""
    global _graph_instance

    if _graph_instance is None:
        _graph_instance = build_interview_graph(checkpointer)

    return _graph_instance
