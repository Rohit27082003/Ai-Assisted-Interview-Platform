"""
Router Module

Exports the deterministic decision router and related utilities.
"""

from .decision_router import (
    DecisionRouter,
    RouterConfig,
    GuardCondition,
    GuardResult,
    evaluate_guard,
    get_decision_router,
    make_routing_decision,
    DEFAULT_CONFIG,
)

__all__ = [
    "DecisionRouter",
    "RouterConfig",
    "GuardCondition",
    "GuardResult",
    "evaluate_guard",
    "get_decision_router",
    "make_routing_decision",
    "DEFAULT_CONFIG",
]
