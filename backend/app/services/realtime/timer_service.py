"""
Server-Side Timer Service

Manages interview timing with WebSocket broadcasts.
Provides centralized timing authority for security and consistency.
"""

import asyncio
from starlette.websockets import WebSocketState
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


class InterviewTimer:
    """Manages timing for a single interview session."""

    def __init__(
        self,
        interview_id: str,
        websocket,
        reading_seconds: int = 20,
        answer_seconds: int = 45,
    ):
        self.interview_id = interview_id
        self.websocket = websocket
        self.reading_seconds = reading_seconds
        self.answer_seconds = answer_seconds

        self.phase = 'idle'  # idle, reading, answering
        self.time_left = 0
        self.task: Optional[asyncio.Task] = None
        self.stopped = False

    async def start_reading_phase(self):
        """Start the reading phase timer."""
        if self.task and not self.task.done():
            self.task.cancel()

        self.phase = 'reading'
        self.time_left = self.reading_seconds
        self.stopped = False

        logger.info(f"Starting reading phase for {self.interview_id}: {self.reading_seconds}s")
        self.task = asyncio.create_task(self._run_timer())

    async def start_answering_phase(self):
        """Start the answering phase timer."""
        if self.task and not self.task.done():
            self.task.cancel()

        self.phase = 'answering'
        self.time_left = self.answer_seconds
        self.stopped = False

        logger.info(f"Starting answering phase for {self.interview_id}: {self.answer_seconds}s")
        self.task = asyncio.create_task(self._run_timer())

    async def stop(self):
        """Stop the timer."""
        self.stopped = True
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info(f"Timer stopped for {self.interview_id}")

    async def _run_timer(self):
        """Run the timer countdown and broadcast updates."""
        try:
            while self.time_left > 0 and not self.stopped:
                # Send timer update
                await self._broadcast_timer()

                # Wait 1 second
                await asyncio.sleep(1)
                self.time_left -= 1

            # Timer expired
            if not self.stopped and self.time_left == 0:
                await self._handle_timer_expiry()

        except asyncio.CancelledError:
            logger.debug(f"Timer cancelled for {self.interview_id}")
        except Exception as e:
            logger.error(f"Timer error for {self.interview_id}: {e}", exc_info=True)

    async def _broadcast_timer(self):
        """Broadcast current timer state to client."""
        try:
            
            if self.websocket and self.websocket.client_state != WebSocketState.DISCONNECTED:
                await self.websocket.send_json({
                    'type': 'timer',
                    'data': {
                        'seconds_left': self.time_left,
                        'phase': self.phase,
                        'auto_closed': False,
                    }
                })
        except Exception as e:
            logger.error(f"Timer broadcast error for {self.interview_id}: {e}")

    async def _handle_timer_expiry(self):
        """Handle timer expiration - transition phase or auto-submit."""
        logger.info(f"Timer expired for {self.interview_id}: phase={self.phase}")

        try:
            if self.phase == 'reading':
                # Transition to answering phase
                await self.websocket.send_json({
                    'type': 'timer',
                    'data': {
                        'seconds_left': 0,
                        'phase': 'reading',
                        'auto_closed': False,
                    }
                })
                # Answering phase will be started by the frontend
                # or the graph will handle it

            elif self.phase == 'answering':
                # Auto-submit answer
                await self.websocket.send_json({
                    'type': 'timer',
                    'data': {
                        'seconds_left': 0,
                        'phase': 'answering',
                        'auto_closed': True,  # Signal auto-submit
                    }
                })

        except Exception as e:
            logger.error(f"Timer expiry handling error for {self.interview_id}: {e}")


# Global registry of active timers
_active_timers: Dict[str, InterviewTimer] = {}


def get_or_create_timer(
    interview_id: str,
    websocket,
    reading_seconds: Optional[int] = None,
    answer_seconds: Optional[int] = None,
) -> InterviewTimer:
    """Get or create a timer for an interview."""
    if interview_id not in _active_timers:
        _active_timers[interview_id] = InterviewTimer(
            interview_id,
            websocket,
            reading_seconds=reading_seconds or settings.READING_TIME_SECONDS,
            answer_seconds=answer_seconds or settings.ANSWER_TIME_SECONDS,
        )
    return _active_timers[interview_id]


async def stop_timer(interview_id: str):
    """Stop and remove a timer."""
    if interview_id in _active_timers:
        timer = _active_timers[interview_id]
        await timer.stop()
        del _active_timers[interview_id]
        logger.info(f"Timer removed for {interview_id}")


async def cleanup_all_timers():
    """Stop all active timers (for shutdown)."""
    logger.info(f"Cleaning up {len(_active_timers)} active timers")
    for interview_id in list(_active_timers.keys()):
        await stop_timer(interview_id)
