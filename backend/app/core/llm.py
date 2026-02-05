"""LLM client initialization using Groq via LangChain."""

from langchain_groq import ChatGroq
from app.core.config import get_settings

settings = get_settings()


def get_llm(temperature: float = None, max_tokens: int = None) -> ChatGroq:
    """Get configured Groq LLM instance."""
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=temperature or settings.GROQ_TEMPERATURE,
        max_tokens=max_tokens or settings.GROQ_MAX_TOKENS,
    )


def get_structured_llm(schema, temperature: float = None):
    """Get LLM that outputs structured data conforming to a Pydantic schema."""
    llm = get_llm(temperature=temperature)
    return llm.with_structured_output(schema)
