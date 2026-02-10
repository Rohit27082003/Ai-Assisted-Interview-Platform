from pydantic import BaseModel, Field
from typing import List

class SimpleAnalysisOutput(BaseModel):
    """Simple answer analysis output for the orchestration graph."""
    is_relevant: bool = Field(description="Did the candidate try to answer?")
    correctness_score: int = Field(description="1-10 score of factual accuracy", ge=1, le=10)
    depth_score: int = Field(description="1-5 score of technical depth", ge=1, le=5)
    missing_concepts: List[str] = Field(description="List of key concepts missing from the answer")
    followup_suggested: bool = Field(description="True if gaps need probing OR answer was fascinating")
    cheating_suspicion: int = Field(description="0-10 score (10=Robot/Read from screen)", ge=0, le=10)
