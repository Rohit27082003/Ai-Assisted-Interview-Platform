"""
Centralized Prompts Module

This module provides a single source of truth for all LLM prompts.
Prompts are loaded dynamically and can be customized via configuration.

Architecture:
- All prompts are defined in dedicated files by domain
- PromptRegistry provides centralized access
- Prompts support variable interpolation via {variable} syntax
- All prompts are versioned for reproducibility

Usage:
    from app.prompts import PromptRegistry

    registry = PromptRegistry()
    prompt = registry.get("question_generation",
                          pillar="Data Structures",
                          depth_level=3)
"""

from .registry import PromptRegistry, PromptTemplate
from .interview_prompts import INTERVIEW_PROMPTS
from .analysis_prompts import ANALYSIS_PROMPTS
from .evaluation_prompts import EVALUATION_PROMPTS
from .reporting_prompts import REPORTING_PROMPTS

__all__ = [
    "PromptRegistry",
    "PromptTemplate",
    "INTERVIEW_PROMPTS",
    "ANALYSIS_PROMPTS",
    "EVALUATION_PROMPTS",
    "REPORTING_PROMPTS",
]
