from pydantic import BaseModel, Field

class CheatingCheckOutput(BaseModel):
    """Output for LLM cheating detection check."""
    suspicious: bool = Field(description="True if the answer appears suspicious")
    reason: str = Field(description="Explanation of why the answer is suspicious")
