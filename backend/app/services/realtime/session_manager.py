import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import WebSocket

# Active sessions storage
# interview_id -> { "websocket": WebSocket, "connected_at": datetime, "terminated": bool, ... }
active_sessions: Dict[str, Dict[str, Any]] = {}

# Pending cleanup tasks
# interview_id -> asyncio.Task
pending_cleanups: Dict[str, asyncio.Task] = {}

def register_session(interview_id: str, websocket: WebSocket, metadata: Optional[Dict] = None):
    """Register a new active WebSocket session."""
    session_data = {
        "websocket": websocket,
        "connected_at": datetime.now(timezone.utc),
        "terminated": False,
        "stream_id": f"stream-{interview_id}",
        "answer_buffer": "",
    }
    if metadata:
        session_data.update(metadata)
    
    active_sessions[interview_id] = session_data
    
    # Cancel any pending cleanup
    if interview_id in pending_cleanups:
        pending_cleanups[interview_id].cancel()
        pending_cleanups.pop(interview_id, None)

def get_session(interview_id: str) -> Optional[Dict[str, Any]]:
    """Get active session data."""
    return active_sessions.get(interview_id)

def remove_session(interview_id: str):
    """Remove a session (e.g. on disconnect)."""
    active_sessions.pop(interview_id, None)

def mark_terminated(interview_id: str):
    """Mark a session as terminated."""
    if interview_id in active_sessions:
        active_sessions[interview_id]["terminated"] = True

def schedule_cleanup(interview_id: str, task: asyncio.Task):
    """Schedule a cleanup task."""
    pending_cleanups[interview_id] = task
