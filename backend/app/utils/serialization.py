"""Serialization utilities for LangGraph state."""

from typing import Any, Dict


def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to serialize LangGraph state for JSON storage.

    Handles Pydantic models and other objects with model_dump/dict methods
    found in LangGraph state values (e.g., BaseMessage objects).
    """
    serialized = {}
    for k, v in state.items():
        if isinstance(v, list):
            new_list = []
            for item in v:
                if hasattr(item, "model_dump"):
                    new_list.append(item.model_dump())
                elif hasattr(item, "dict"):
                    new_list.append(item.dict())
                else:
                    new_list.append(item)
            serialized[k] = new_list
        elif hasattr(v, "model_dump"):
            serialized[k] = v.model_dump()
        elif hasattr(v, "dict"):
            serialized[k] = v.dict()
        else:
            serialized[k] = v
    return serialized
