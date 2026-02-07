"""
Structured Output Schemas for LLM Responses

This module defines Pydantic schemas for all LLM outputs.
These schemas enforce typed, validated responses and eliminate
manual parsing (regex, string splitting, untyped JSON).

Usage with LangChain:
    from langchain_core.output_parsers import PydanticOutputParser
    parser = PydanticOutputParser(pydantic_object=QuestionGenerationOutput)
    llm_with_parser = llm.with_structured_output(QuestionGenerationOutput)
"""

from .question_outputs import (
    QuestionGenerationOutput,
    FollowUpDecisionOutput,
)
from .analysis_outputs import (
    AnswerAnalysisOutput,
    CheatingDetectionOutput,
)
from .evaluation_outputs import (
    ReferenceAnswerOutput,
    RubricScoringOutput,
    EvaluationAggregateOutput,
)
from .reporting_outputs import (
    PerformanceAnalysisOutput,
    RecommendationOutput,
    FinalReportOutput,
)

__all__ = [
    # Question generation
    "QuestionGenerationOutput",
    "FollowUpDecisionOutput",
    # Answer analysis
    "AnswerAnalysisOutput",
    "CheatingDetectionOutput",
    # Evaluation
    "ReferenceAnswerOutput",
    "RubricScoringOutput",
    "EvaluationAggregateOutput",
    # Reporting
    "PerformanceAnalysisOutput",
    "RecommendationOutput",
    "FinalReportOutput",
]
