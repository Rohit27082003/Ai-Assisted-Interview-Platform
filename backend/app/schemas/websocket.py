"""Pydantic schemas for WebSocket messages."""

from typing import Dict, Any
from pydantic import BaseModel


class WSMessage(BaseModel):
    type: str  # question, timer, transcript, cheating_warning, complete, error
    data: Dict[str, Any]


class WSAudioChunk(BaseModel):
    interview_id: str
    chunk: str  # base64 encoded audio
    sequence: int
