"""
Deterministic Decision Router

This module implements a rule-first, deterministic router that controls
all interview flow decisions. Key principles:

1. ONLY the router can terminate an interview
2. All decisions are based on state guards, not direct node branching
3. Rules are evaluated in priority order
4. LLM assistance is optional and only for edge cases
5. All decisions are logged for observability

Termination Conditions (evaluated in priority order):
1. Hard violation detected (cheating penalty level)
2. Recruiter termination request
3. Interview timeout
4. All pillars completed
5. Maximum questions reached
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.state import (
    InterviewState,
    RouterDecision,
    InterviewPhase,
    CheatingLevel,
    log_transition,
    get_current_pillar,
)
from app.core.logging import get_logger
from app.utils.datetime_helpers import parse_iso_datetime

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTER CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RouterConfig:
    """Configuration for the decision router."""

    # Question limits
    max_questions_per_pillar: int = 5   # Total questions per topic INCLUDING follow-ups
    max_follow_ups_per_pillar: int = 4  # Max 3-4 follow-ups per topic
    max_total_questions: int = 25

    # Cheating thresholds
    cheating_warning_threshold: float = 5.0
    cheating_penalty_threshold: float = 8.0

    # Score thresholds for difficulty progression
    high_score_threshold: float = 7.0  # Increase difficulty
    low_score_threshold: float = 4.0   # Don't increase difficulty

    # Follow-up thresholds
    follow_up_depth_threshold: float = 6.0  # Minimum depth to consider follow-up
    follow_up_gap_threshold: float = 0.5    # Minimum gap indication

    # Timing (in minutes)
    interview_timeout_minutes: int = 60


DEFAULT_CONFIG = RouterConfig()


# ═══════════════════════════════════════════════════════════════════════════════
# GUARD CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════════


class GuardCondition(Enum):
    """Named guard conditions for clarity."""
    HARD_VIOLATION = "hard_violation"
    RECRUITER_TERMINATION = "recruiter_termination"
    INTERVIEW_TIMEOUT = "interview_timeout"
    ALL_PILLARS_COMPLETE = "all_pillars_complete"
    MAX_QUESTIONS_REACHED = "max_questions_reached"
    PILLAR_COMPLETE = "pillar_complete"
    SHOULD_FOLLOW_UP = "should_follow_up"
    CONTINUE_PILLAR = "continue_pillar"


@dataclass
class GuardResult:
    """Result of evaluating a guard condition."""
    condition: GuardCondition
    triggered: bool
    reason: str
    priority: int  # Lower = higher priority
    metadata: Optional[Dict[str, Any]] = None


def evaluate_guard(
    condition: GuardCondition,
    state: InterviewState,
    config: RouterConfig = DEFAULT_CONFIG,
) -> GuardResult:
    """
    Evaluate a single guard condition against state.

    Args:
        condition: The guard to evaluate
        state: Current interview state
        config: Router configuration

    Returns:
        GuardResult with triggered status and reason
    """
    evaluators = {
        GuardCondition.HARD_VIOLATION: _check_hard_violation,
        GuardCondition.RECRUITER_TERMINATION: _check_recruiter_termination,
        GuardCondition.INTERVIEW_TIMEOUT: _check_interview_timeout,
        GuardCondition.ALL_PILLARS_COMPLETE: _check_all_pillars_complete,
        GuardCondition.MAX_QUESTIONS_REACHED: _check_max_questions,
        GuardCondition.PILLAR_COMPLETE: _check_pillar_complete,
        GuardCondition.SHOULD_FOLLOW_UP: _check_should_follow_up,
        GuardCondition.CONTINUE_PILLAR: _check_continue_pillar,
    }

    evaluator = evaluators.get(condition)
    if not evaluator:
        return GuardResult(
            condition=condition,
            triggered=False,
            reason=f"Unknown condition: {condition}",
            priority=999,
        )

    return evaluator(state, config)


def _check_hard_violation(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Check if a hard cheating violation has occurred."""
    cheating_level = state.get("cheating_level", CheatingLevel.NONE.value)
    cheating_score = state.get("cheating_score", 0.0)

    term_conditions = state.get("termination_conditions", {})
    hard_violation = term_conditions.get("hard_violation_detected", False)
    violation_reason = term_conditions.get("violation_reason")

    triggered = (
        cheating_level == CheatingLevel.PENALTY.value
        or cheating_score >= config.cheating_penalty_threshold
        or hard_violation
    )

    return GuardResult(
        condition=GuardCondition.HARD_VIOLATION,
        triggered=triggered,
        reason=violation_reason or f"Cheating score {cheating_score:.1f} exceeds threshold",
        priority=1,  # Highest priority
        metadata={"cheating_level": cheating_level, "cheating_score": cheating_score},
    )


def _check_recruiter_termination(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Check if recruiter has requested termination."""
    term_conditions = state.get("termination_conditions", {})
    recruiter_terminated = term_conditions.get("recruiter_terminated", False)
    reason = term_conditions.get("recruiter_termination_reason", "Recruiter requested termination")

    return GuardResult(
        condition=GuardCondition.RECRUITER_TERMINATION,
        triggered=recruiter_terminated,
        reason=reason,
        priority=2,
    )


def _check_interview_timeout(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Check if interview has exceeded time limit."""
    timing = state.get("timing", {})
    interview_started = timing.get("interview_started_at")

    if not interview_started:
        return GuardResult(
            condition=GuardCondition.INTERVIEW_TIMEOUT,
            triggered=False,
            reason="Interview not yet started",
            priority=3,
        )

    start_time = parse_iso_datetime(interview_started)

    now = datetime.now(timezone.utc)
    elapsed_minutes = (now - start_time).total_seconds() / 60
    timeout = config.interview_timeout_minutes

    triggered = elapsed_minutes >= timeout

    return GuardResult(
        condition=GuardCondition.INTERVIEW_TIMEOUT,
        triggered=triggered,
        reason=f"Interview duration {elapsed_minutes:.1f} minutes (limit: {timeout})",
        priority=3,
        metadata={"elapsed_minutes": elapsed_minutes, "timeout_minutes": timeout},
    )


def _check_all_pillars_complete(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Check if all pillars have been completed."""
    focus_areas = state.get("focus_areas", [])
    current_idx = state.get("current_pillar_index", 0)
    total_pillars = len(focus_areas)

    # Check if we've gone through all pillars
    all_complete = current_idx >= total_pillars

    # Also check if all pillars are marked complete
    if not all_complete:
        all_complete = all(fa.get("completed", False) for fa in focus_areas)

    return GuardResult(
        condition=GuardCondition.ALL_PILLARS_COMPLETE,
        triggered=all_complete,
        reason=f"Completed {current_idx}/{total_pillars} pillars",
        priority=4,
        metadata={"current_pillar_index": current_idx, "total_pillars": total_pillars},
    )


def _check_max_questions(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Check if maximum total questions have been asked."""
    total_asked = state.get("total_questions_asked", 0)
    max_questions = state.get("max_total_questions", config.max_total_questions)

    triggered = total_asked >= max_questions

    return GuardResult(
        condition=GuardCondition.MAX_QUESTIONS_REACHED,
        triggered=triggered,
        reason=f"Asked {total_asked}/{max_questions} questions",
        priority=5,
        metadata={"total_asked": total_asked, "max_questions": max_questions},
    )


def _check_pillar_complete(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Check if current pillar is complete.

    Total questions per pillar = initial questions + follow-ups.
    Both count toward the max_questions_per_pillar limit (default 5).
    """
    questions_in_pillar = state.get("questions_in_current_pillar", 0)
    follow_ups_in_pillar = state.get("follow_ups_in_current_pillar", 0)
    total_in_pillar = questions_in_pillar + follow_ups_in_pillar
    max_per_pillar = state.get("max_questions_per_pillar", config.max_questions_per_pillar)

    current_pillar = get_current_pillar(state)
    if current_pillar and current_pillar.get("completed"):
        return GuardResult(
            condition=GuardCondition.PILLAR_COMPLETE,
            triggered=True,
            reason="Pillar marked as complete",
            priority=6,
        )

    triggered = total_in_pillar >= max_per_pillar

    return GuardResult(
        condition=GuardCondition.PILLAR_COMPLETE,
        triggered=triggered,
        reason=f"Asked {total_in_pillar}/{max_per_pillar} in pillar (initial={questions_in_pillar}, follow-ups={follow_ups_in_pillar})",
        priority=6,
        metadata={"total_in_pillar": total_in_pillar, "max_per_pillar": max_per_pillar},
    )


def _check_should_follow_up(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Check if a follow-up question is appropriate.

    Follow-ups are limited per pillar (max 4) AND the total questions
    in the pillar (initial + follow-ups) cannot exceed max_questions_per_pillar (5).
    """
    follow_ups_in_pillar = state.get("follow_ups_in_current_pillar", 0)
    questions_in_pillar = state.get("questions_in_current_pillar", 0)
    total_in_pillar = questions_in_pillar + follow_ups_in_pillar
    max_follow_ups = state.get("max_follow_ups_per_pillar", config.max_follow_ups_per_pillar)
    max_per_pillar = state.get("max_questions_per_pillar", config.max_questions_per_pillar)

    # Can't follow up if we've used all follow-ups for this pillar
    if follow_ups_in_pillar >= max_follow_ups:
        return GuardResult(
            condition=GuardCondition.SHOULD_FOLLOW_UP,
            triggered=False,
            reason=f"Used {follow_ups_in_pillar}/{max_follow_ups} follow-ups in pillar",
            priority=7,
        )

    # Can't follow up if the pillar would exceed its total question limit
    if total_in_pillar + 1 > max_per_pillar:
        return GuardResult(
            condition=GuardCondition.SHOULD_FOLLOW_UP,
            triggered=False,
            reason=f"Pillar at capacity: {total_in_pillar}/{max_per_pillar} questions",
            priority=7,
        )

    # Check analysis signals for follow-up indicators
    signals = state.get("last_analysis_signals", {})
    has_gaps = signals.get("has_probeable_gaps", False)
    depth_score = signals.get("depth_score", 10.0)

    # Rule: Follow up if there are gaps AND depth score suggests partial understanding
    triggered = (
        has_gaps
        and config.low_score_threshold < depth_score < config.high_score_threshold
    )

    follow_ups_remaining = min(max_follow_ups - follow_ups_in_pillar, max_per_pillar - total_in_pillar)
    return GuardResult(
        condition=GuardCondition.SHOULD_FOLLOW_UP,
        triggered=triggered,
        reason=f"Gaps: {has_gaps}, Depth: {depth_score:.1f}, Follow-ups left: {follow_ups_remaining}",
        priority=7,
        metadata={
            "has_gaps": has_gaps,
            "depth_score": depth_score,
            "follow_ups_remaining": follow_ups_remaining,
        },
    )


def _check_continue_pillar(state: InterviewState, config: RouterConfig) -> GuardResult:
    """Default condition - continue with current pillar."""
    return GuardResult(
        condition=GuardCondition.CONTINUE_PILLAR,
        triggered=True,  # Always available as fallback
        reason="Continue with next question in pillar",
        priority=8,  # Lowest priority
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ═══════════════════════════════════════════════════════════════════════════════


class DecisionRouter:
    """
    Deterministic decision router for interview flow control.

    This router evaluates all guard conditions in priority order
    and returns the appropriate routing decision. It is the ONLY
    component that can determine interview termination.
    """

    def __init__(self, config: Optional[RouterConfig] = None):
        """Initialize router with configuration."""
        self.config = config or DEFAULT_CONFIG
        self._decision_count = 0

    def decide(self, state: InterviewState) -> Tuple[RouterDecision, InterviewState]:
        """
        Make a routing decision based on current state.

        This is the main entry point for flow control. It evaluates
        all guard conditions and returns the appropriate decision.

        Args:
            state: Current interview state

        Returns:
            Tuple of (RouterDecision, updated InterviewState)
        """
        self._decision_count += 1
        from_phase = state.get("phase", InterviewPhase.QUESTIONING.value)

        # Evaluate all guards in priority order
        guards_to_check = [
            GuardCondition.HARD_VIOLATION,
            GuardCondition.RECRUITER_TERMINATION,
            GuardCondition.INTERVIEW_TIMEOUT,
            GuardCondition.ALL_PILLARS_COMPLETE,
            GuardCondition.MAX_QUESTIONS_REACHED,
            GuardCondition.PILLAR_COMPLETE,
            GuardCondition.SHOULD_FOLLOW_UP,
            GuardCondition.CONTINUE_PILLAR,
        ]

        results: List[GuardResult] = []
        for guard in guards_to_check:
            result = evaluate_guard(guard, state, self.config)
            results.append(result)

            logger.debug(
                f"Guard {guard.value}: triggered={result.triggered}, "
                f"reason={result.reason}"
            )

        # Find first triggered guard (sorted by priority)
        triggered = sorted(
            [r for r in results if r.triggered],
            key=lambda r: r.priority,
        )

        if not triggered:
            # Should never happen due to CONTINUE_PILLAR fallback
            logger.warning("No guard triggered, defaulting to CONTINUE_PILLAR")
            decision = RouterDecision.CONTINUE_PILLAR
            reason = "Default fallback"
        else:
            first = triggered[0]
            decision = self._guard_to_decision(first.condition)
            reason = first.reason

            logger.info(
                f"Router decision #{self._decision_count}: {decision.value} "
                f"(guard: {first.condition.value}, reason: {reason})"
            )

        # Update state with decision
        to_phase = self._decision_to_phase(decision)
        updated_state = self._update_state_with_decision(
            state, decision, from_phase, to_phase, reason, results
        )

        return decision, updated_state

    def _guard_to_decision(self, guard: GuardCondition) -> RouterDecision:
        """Map guard condition to router decision."""
        mapping = {
            GuardCondition.HARD_VIOLATION: RouterDecision.END_VIOLATION,
            GuardCondition.RECRUITER_TERMINATION: RouterDecision.END_RECRUITER,
            GuardCondition.INTERVIEW_TIMEOUT: RouterDecision.END_TIMEOUT,
            GuardCondition.ALL_PILLARS_COMPLETE: RouterDecision.END_COMPLETE,
            GuardCondition.MAX_QUESTIONS_REACHED: RouterDecision.END_COMPLETE,
            GuardCondition.PILLAR_COMPLETE: RouterDecision.NEXT_PILLAR,
            GuardCondition.SHOULD_FOLLOW_UP: RouterDecision.FOLLOW_UP,
            GuardCondition.CONTINUE_PILLAR: RouterDecision.CONTINUE_PILLAR,
        }
        return mapping.get(guard, RouterDecision.CONTINUE_PILLAR)

    def _decision_to_phase(self, decision: RouterDecision) -> str:
        """Map router decision to interview phase."""
        if decision in [
            RouterDecision.END_COMPLETE,
            RouterDecision.END_VIOLATION,
            RouterDecision.END_TIMEOUT,
            RouterDecision.END_RECRUITER,
        ]:
            return InterviewPhase.COMPLETED.value if decision == RouterDecision.END_COMPLETE else InterviewPhase.TERMINATED.value

        if decision == RouterDecision.NEXT_PILLAR:
            return InterviewPhase.TRANSITIONING.value

        return InterviewPhase.QUESTIONING.value

    def _update_state_with_decision(
        self,
        state: InterviewState,
        decision: RouterDecision,
        from_phase: str,
        to_phase: str,
        reason: str,
        guard_results: List[GuardResult],
    ) -> InterviewState:
        """Update state with the routing decision."""
        # Log transition
        updated = log_transition(
            state,
            from_phase=from_phase,
            to_phase=to_phase,
            node_name="decision_router",
            router_decision=decision.value,
            details={
                "reason": reason,
                "decision_number": self._decision_count,
                "guards_evaluated": [
                    {"guard": r.condition.value, "triggered": r.triggered}
                    for r in guard_results
                ],
            },
        )

        # Update router decision and phase
        updated = {
            **updated,
            "router_decision": decision.value,
            "phase": to_phase,
        }

        # Update termination conditions if ending
        if decision in [
            RouterDecision.END_COMPLETE,
            RouterDecision.END_VIOLATION,
            RouterDecision.END_TIMEOUT,
            RouterDecision.END_RECRUITER,
        ]:
            term_conditions = updated.get("termination_conditions", {}).copy()

            if decision == RouterDecision.END_COMPLETE:
                term_conditions["all_pillars_completed"] = True
            elif decision == RouterDecision.END_VIOLATION:
                term_conditions["hard_violation_detected"] = True
                term_conditions["violation_reason"] = reason
            elif decision == RouterDecision.END_TIMEOUT:
                term_conditions["interview_timeout"] = True

            updated["termination_conditions"] = term_conditions

        return updated

    def request_termination(
        self,
        state: InterviewState,
        reason: str,
        termination_type: str = "recruiter",
    ) -> InterviewState:
        """
        Request interview termination (used by recruiters).

        Args:
            state: Current interview state
            reason: Reason for termination
            termination_type: Type of termination ("recruiter", "violation", "timeout")

        Returns:
            Updated state with termination request
        """
        term_conditions = state.get("termination_conditions", {}).copy()

        if termination_type == "recruiter":
            term_conditions["recruiter_terminated"] = True
            term_conditions["recruiter_termination_reason"] = reason
        elif termination_type == "violation":
            term_conditions["hard_violation_detected"] = True
            term_conditions["violation_reason"] = reason
        elif termination_type == "timeout":
            term_conditions["interview_timeout"] = True

        return {**state, "termination_conditions": term_conditions}

    def get_difficulty_adjustment(self, state: InterviewState) -> int:
        """
        Determine difficulty adjustment based on last answer.

        Returns:
            -1 (decrease), 0 (maintain), or +1 (increase)
        """
        signals = state.get("last_analysis_signals", {})
        if not signals:
            return 0

        correctness = signals.get("correctness_score", 5.0)

        if correctness >= self.config.high_score_threshold:
            return 1  # Increase difficulty
        elif correctness <= self.config.low_score_threshold:
            return -1  # Decrease difficulty

        return 0  # Maintain current level


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════


_router_instance: Optional[DecisionRouter] = None


def get_decision_router(config: Optional[RouterConfig] = None) -> DecisionRouter:
    """Get the global decision router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = DecisionRouter(config)
    return _router_instance


def make_routing_decision(state: InterviewState) -> Tuple[RouterDecision, InterviewState]:
    """Convenience function to make a routing decision."""
    return get_decision_router().decide(state)
