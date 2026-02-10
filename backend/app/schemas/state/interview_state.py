"""
Centralized Interview State Schema

This module defines the single source of truth for interview state.
All graph nodes read from and write to this state structure.
State is persisted in PostgreSQL JSONB for resumability.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from .enums import InterviewPhase, RouterDecision, CheatingLevel
from .models import (
    FocusArea,
    QuestionRecord,
    CheatingFlag,
    StateTransitionLog,
    TimingState,
    TerminationConditions,
)


class InterviewState(TypedDict, total=False):
    """
    The single, strongly-typed interview state schema.

    This state is:
    - Persisted in PostgreSQL JSONB via LangGraph checkpointing
    - The single source of truth for all graph nodes
    - Resumable after failures
    - Fully observable for debugging

    All graph transitions are state-based. Nodes mutate and return state.
    No node can directly end the interview - only the decision router can.
    """

    # ─── Identity ─────────────────────────────────────────────────────────────
    interview_id: str
    candidate_id: str
    jd_id: str

    # ─── Context (Immutable after init) ───────────────────────────────────────
    candidate_name: str
    candidate_email: str
    job_role: str
    job_requirements: Dict[str, Any]  # Parsed JD object
    resume_context: str  # Extracted resume text

    # ─── Pillars/Focus Areas ──────────────────────────────────────────────────
    focus_areas: List[Dict[str, Any]]  # List of FocusArea dicts
    current_pillar_index: int
    total_pillars: int

    # ─── Current Question State ───────────────────────────────────────────────
    current_question_id: Optional[str]
    current_question: Optional[str]
    current_question_depth: int  # 1-5
    awaiting_answer: bool

    # ─── Conversation Memory ──────────────────────────────────────────────────
    # Annotated list for LangGraph append-only semantics
    message_history: Annotated[List[BaseMessage], operator.add]

    # Full question-answer records for context and persistence
    question_records: List[Dict[str, Any]]  # List of QuestionRecord dicts

    # ─── Analysis Signals ─────────────────────────────────────────────────────
    last_analysis_signals: Optional[Dict[str, Any]]
    cumulative_scores: Dict[str, float]  # Pillar -> cumulative score

    # ─── Cheating Detection ───────────────────────────────────────────────────
    cheating_flags: List[Dict[str, Any]]  # List of CheatingFlag dicts
    cheating_level: str  # CheatingLevel enum value
    cheating_score: float  # 0-10 cumulative

    # ─── Timing ───────────────────────────────────────────────────────────────
    timing: Dict[str, Any]  # TimingState dict

    # ─── Flow Control ─────────────────────────────────────────────────────────
    phase: str  # InterviewPhase enum value
    router_decision: str  # RouterDecision enum value
    termination_conditions: Dict[str, Any]  # TerminationConditions dict

    # ─── Counters ─────────────────────────────────────────────────────────────
    total_questions_asked: int
    total_follow_ups: int
    questions_in_current_pillar: int
    follow_ups_in_current_pillar: int

    # ─── Configuration ────────────────────────────────────────────────────────
    max_questions_per_pillar: int
    max_follow_ups_per_question: int
    max_total_questions: int
    difficulty_progression_enabled: bool

    # ─── Error Handling ───────────────────────────────────────────────────────
    error_count: int
    last_error: Optional[str]

    # ─── Observability ────────────────────────────────────────────────────────
    transition_log: List[Dict[str, Any]]  # List of StateTransitionLog dicts

    # ─── Metadata ─────────────────────────────────────────────────────────────
    created_at: str  # ISO timestamp
    updated_at: str  # ISO timestamp
    version: int  # For optimistic locking

    # ─── Ephemeral / Injected (Not persisted or transient) ────────────────────
    _injected_answer_text: Optional[str]
    _injected_audio_url: Optional[str]
