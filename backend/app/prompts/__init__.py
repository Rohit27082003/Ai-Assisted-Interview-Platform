"""
Centralized Prompts Module

This module provides a single source of truth for all LLM prompts.
Prompts are loaded dynamically and can be customized via configuration.

Architecture:
- All prompts are defined in dedicated files by domain
- Prompts are exported as ChatPromptTemplate objects
- Prompts support variable interpolation via {variable} syntax

Usage:
    from app.prompts import QUESTION_GENERATION_PROMPT
    
    chain = QUESTION_GENERATION_PROMPT | llm
    result = await chain.ainvoke({...})
"""

from .question_prompts import (
    QUESTION_GENERATION_PROMPT,
    FOLLOW_UP_QUESTION_PROMPT,
    FOLLOW_UP_DECISION_PROMPT,
)

from .orchestration_prompts import (
    PILLAR_TRANSITION_PROMPT,
    INTERVIEW_INTRODUCTION_PROMPT,
    INTERVIEW_CONCLUSION_PROMPT,
)

from .analysis_prompts import (
    ANSWER_ANALYSIS_PROMPT,
    CHEATING_DETECTION_PROMPT,
    CHEATING_ESCALATION_PROMPT,
    QUICK_RELEVANCE_CHECK_PROMPT,
)

from .evaluation_prompts import (
    REFERENCE_ANSWER_PROMPT,
    RUBRIC_SCORING_PROMPT,
    EVALUATION_AGGREGATE_PROMPT,
    BATCH_REFERENCE_GENERATION_PROMPT,
)

from .reporting_prompts import (
    PERFORMANCE_ANALYSIS_PROMPT,
    HIRING_RECOMMENDATION_PROMPT,
    EXECUTIVE_SUMMARY_PROMPT,
    PILLAR_FEEDBACK_PROMPT,
    COMPILE_FINAL_REPORT_PROMPT,
)

__all__ = [
    # Interview
    "QUESTION_GENERATION_PROMPT",
    "FOLLOW_UP_QUESTION_PROMPT",
    "FOLLOW_UP_DECISION_PROMPT",
    "PILLAR_TRANSITION_PROMPT",
    "INTERVIEW_INTRODUCTION_PROMPT",
    "INTERVIEW_CONCLUSION_PROMPT",
    
    # Analysis
    "ANSWER_ANALYSIS_PROMPT",
    "CHEATING_DETECTION_PROMPT",
    "CHEATING_ESCALATION_PROMPT",
    "QUICK_RELEVANCE_CHECK_PROMPT",
    
    # Evaluation
    "REFERENCE_ANSWER_PROMPT",
    "RUBRIC_SCORING_PROMPT",
    "EVALUATION_AGGREGATE_PROMPT",
    "BATCH_REFERENCE_GENERATION_PROMPT",
    
    # Reporting
    "PERFORMANCE_ANALYSIS_PROMPT",
    "HIRING_RECOMMENDATION_PROMPT",
    "EXECUTIVE_SUMMARY_PROMPT",
    "PILLAR_FEEDBACK_PROMPT",
    "COMPILE_FINAL_REPORT_PROMPT",
]
