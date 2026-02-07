"""
Interview Broadcaster - Real-time Recruiter Visibility

Provides WebSocket/SSE streaming for recruiter dashboards to receive:
- Current pillar and question number
- Transcript snippets
- Cheating flags
- Interview status updates
- State transitions

Architecture:
- Events are persisted BEFORE broadcasting (consistency guarantee)
- Supports multiple recruiters per interview
- Backpressure handling for slow clients
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT TYPES
# ═══════════════════════════════════════════════════════════════════════════════


class InterviewEventType(str, Enum):
    """Types of events broadcast to recruiters."""
    # Lifecycle events
    INTERVIEW_STARTED = "interview_started"
    INTERVIEW_COMPLETED = "interview_completed"
    INTERVIEW_TERMINATED = "interview_terminated"

    # Progress events
    PILLAR_STARTED = "pillar_started"
    PILLAR_COMPLETED = "pillar_completed"
    QUESTION_ASKED = "question_asked"
    ANSWER_RECEIVED = "answer_received"
    ANSWER_ANALYZED = "answer_analyzed"

    # Safety events
    CHEATING_FLAG = "cheating_flag"
    CHEATING_WARNING = "cheating_warning"
    CHEATING_PENALTY = "cheating_penalty"

    # Status events
    STATE_TRANSITION = "state_transition"
    ERROR_OCCURRED = "error_occurred"

    # Timing events
    READING_STARTED = "reading_started"
    ANSWER_STARTED = "answer_started"
    TIMEOUT_WARNING = "timeout_warning"


class InterviewEvent(BaseModel):
    """A single interview event for broadcasting."""
    event_id: str
    event_type: InterviewEventType
    interview_id: str
    timestamp: datetime
    data: Dict[str, Any]

    class Config:
        use_enum_values = True


# ═══════════════════════════════════════════════════════════════════════════════
# CONNECTION MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RecruiterConnection:
    """A single recruiter WebSocket connection."""
    websocket: WebSocket
    recruiter_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_event_id: Optional[str] = None
    is_active: bool = True


class InterviewBroadcaster:
    """
    Manages real-time event broadcasting to recruiters.

    Features:
    - Multiple recruiters per interview
    - Automatic reconnection support (via last_event_id)
    - Backpressure handling
    - Event persistence before broadcast
    """

    def __init__(self):
        """Initialize the broadcaster."""
        # interview_id -> set of connections
        self._connections: Dict[str, Set[RecruiterConnection]] = {}

        # interview_id -> list of recent events (for catch-up)
        self._event_buffer: Dict[str, List[InterviewEvent]] = {}
        self._buffer_max_size = 100

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Event persistence callback (set by application)
        self._persist_callback: Optional[Callable[[InterviewEvent], asyncio.Future]] = None

    def set_persist_callback(
        self,
        callback: Callable[[InterviewEvent], asyncio.Future],
    ) -> None:
        """Set the callback for persisting events before broadcast."""
        self._persist_callback = callback

    async def connect(
        self,
        websocket: WebSocket,
        interview_id: str,
        recruiter_id: str,
        last_event_id: Optional[str] = None,
    ) -> RecruiterConnection:
        """
        Connect a recruiter to receive interview updates.

        Args:
            websocket: The WebSocket connection
            interview_id: Interview to subscribe to
            recruiter_id: Recruiter's ID
            last_event_id: Last received event (for catch-up)

        Returns:
            The connection object
        """
        await websocket.accept()

        connection = RecruiterConnection(
            websocket=websocket,
            recruiter_id=recruiter_id,
            last_event_id=last_event_id,
        )

        async with self._lock:
            if interview_id not in self._connections:
                self._connections[interview_id] = set()
            self._connections[interview_id].add(connection)

        logger.info(
            f"Recruiter {recruiter_id} connected to interview {interview_id}"
        )

        # Send catch-up events if reconnecting
        if last_event_id:
            await self._send_catchup_events(connection, interview_id, last_event_id)

        return connection

    async def disconnect(
        self,
        connection: RecruiterConnection,
        interview_id: str,
    ) -> None:
        """Disconnect a recruiter."""
        connection.is_active = False

        async with self._lock:
            if interview_id in self._connections:
                self._connections[interview_id].discard(connection)
                if not self._connections[interview_id]:
                    del self._connections[interview_id]

        logger.info(
            f"Recruiter {connection.recruiter_id} disconnected from interview {interview_id}"
        )

    async def broadcast(
        self,
        interview_id: str,
        event_type: InterviewEventType,
        data: Dict[str, Any],
    ) -> InterviewEvent:
        """
        Broadcast an event to all connected recruiters.

        Events are persisted BEFORE being broadcast to ensure consistency.

        Args:
            interview_id: The interview ID
            event_type: Type of event
            data: Event payload

        Returns:
            The created event
        """
        import uuid

        event = InterviewEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            interview_id=interview_id,
            timestamp=datetime.utcnow(),
            data=data,
        )

        # Persist first (if callback set)
        if self._persist_callback:
            try:
                await self._persist_callback(event)
            except Exception as e:
                logger.error(f"Failed to persist event: {e}")
                # Continue with broadcast even if persistence fails

        # Add to buffer
        await self._add_to_buffer(interview_id, event)

        # Broadcast to all connections
        async with self._lock:
            connections = self._connections.get(interview_id, set()).copy()

        if connections:
            await self._send_to_connections(connections, event)

        logger.debug(
            f"Broadcast {event_type.value} to {len(connections)} recruiters "
            f"for interview {interview_id}"
        )

        return event

    async def _send_to_connections(
        self,
        connections: Set[RecruiterConnection],
        event: InterviewEvent,
    ) -> None:
        """Send event to all connections with error handling."""
        message = event.model_dump_json()

        tasks = []
        for conn in connections:
            if conn.is_active:
                tasks.append(self._send_single(conn, message, event.event_id))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_single(
        self,
        connection: RecruiterConnection,
        message: str,
        event_id: str,
    ) -> None:
        """Send to a single connection with timeout."""
        try:
            await asyncio.wait_for(
                connection.websocket.send_text(message),
                timeout=5.0,  # 5 second timeout
            )
            connection.last_event_id = event_id
        except asyncio.TimeoutError:
            logger.warning(f"Timeout sending to recruiter {connection.recruiter_id}")
            connection.is_active = False
        except WebSocketDisconnect:
            connection.is_active = False
        except Exception as e:
            logger.error(f"Error sending to recruiter {connection.recruiter_id}: {e}")
            connection.is_active = False

    async def _add_to_buffer(self, interview_id: str, event: InterviewEvent) -> None:
        """Add event to the buffer for catch-up."""
        async with self._lock:
            if interview_id not in self._event_buffer:
                self._event_buffer[interview_id] = []

            self._event_buffer[interview_id].append(event)

            # Trim buffer if needed
            if len(self._event_buffer[interview_id]) > self._buffer_max_size:
                self._event_buffer[interview_id] = self._event_buffer[interview_id][
                    -self._buffer_max_size :
                ]

    async def _send_catchup_events(
        self,
        connection: RecruiterConnection,
        interview_id: str,
        last_event_id: str,
    ) -> None:
        """Send missed events on reconnection."""
        async with self._lock:
            events = self._event_buffer.get(interview_id, [])

        # Find events after last_event_id
        found = False
        catchup_events = []
        for event in events:
            if found:
                catchup_events.append(event)
            elif event.event_id == last_event_id:
                found = True

        if catchup_events:
            logger.info(
                f"Sending {len(catchup_events)} catch-up events to "
                f"recruiter {connection.recruiter_id}"
            )
            for event in catchup_events:
                await self._send_single(
                    connection, event.model_dump_json(), event.event_id
                )

    def get_connection_count(self, interview_id: str) -> int:
        """Get number of active connections for an interview."""
        connections = self._connections.get(interview_id, set())
        return sum(1 for c in connections if c.is_active)

    async def cleanup_interview(self, interview_id: str) -> None:
        """Clean up resources for a completed interview."""
        async with self._lock:
            self._connections.pop(interview_id, None)
            self._event_buffer.pop(interview_id, None)

        logger.info(f"Cleaned up resources for interview {interview_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def create_interview_started_event(
    interview_id: str,
    candidate_name: str,
    job_role: str,
    total_pillars: int,
) -> Dict[str, Any]:
    """Create data for interview started event."""
    return {
        "candidate_name": candidate_name,
        "job_role": job_role,
        "total_pillars": total_pillars,
        "status": "in_progress",
    }


def create_question_asked_event(
    question_number: int,
    pillar_name: str,
    pillar_index: int,
    question_preview: str,
    depth_level: int,
    is_follow_up: bool,
) -> Dict[str, Any]:
    """Create data for question asked event."""
    return {
        "question_number": question_number,
        "pillar_name": pillar_name,
        "pillar_index": pillar_index,
        "question_preview": question_preview[:100] + "..." if len(question_preview) > 100 else question_preview,
        "depth_level": depth_level,
        "is_follow_up": is_follow_up,
    }


def create_answer_analyzed_event(
    question_number: int,
    pillar_name: str,
    score: float,
    summary: str,
    has_concerns: bool,
) -> Dict[str, Any]:
    """Create data for answer analyzed event."""
    return {
        "question_number": question_number,
        "pillar_name": pillar_name,
        "score": round(score, 1),
        "summary": summary[:150] if len(summary) > 150 else summary,
        "has_concerns": has_concerns,
    }


def create_cheating_flag_event(
    question_number: int,
    severity: str,
    reason: str,
    cumulative_score: float,
) -> Dict[str, Any]:
    """Create data for cheating flag event."""
    return {
        "question_number": question_number,
        "severity": severity,
        "reason": reason[:200] if len(reason) > 200 else reason,
        "cumulative_score": round(cumulative_score, 1),
    }


def create_pillar_completed_event(
    pillar_name: str,
    pillar_index: int,
    pillar_score: float,
    questions_asked: int,
    next_pillar: Optional[str],
) -> Dict[str, Any]:
    """Create data for pillar completed event."""
    return {
        "pillar_name": pillar_name,
        "pillar_index": pillar_index,
        "pillar_score": round(pillar_score, 1),
        "questions_asked": questions_asked,
        "next_pillar": next_pillar,
    }


def create_interview_completed_event(
    completion_status: str,
    total_questions: int,
    total_pillars: int,
    duration_minutes: float,
    final_score: Optional[float],
) -> Dict[str, Any]:
    """Create data for interview completed event."""
    return {
        "completion_status": completion_status,
        "total_questions": total_questions,
        "total_pillars": total_pillars,
        "duration_minutes": round(duration_minutes, 1),
        "final_score": round(final_score, 1) if final_score else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════


_broadcaster_instance: Optional[InterviewBroadcaster] = None


def get_broadcaster() -> InterviewBroadcaster:
    """Get the global broadcaster instance."""
    global _broadcaster_instance
    if _broadcaster_instance is None:
        _broadcaster_instance = InterviewBroadcaster()
    return _broadcaster_instance
