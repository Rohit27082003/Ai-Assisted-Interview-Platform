"""AWS Transcribe streaming service for real-time speech-to-text."""

import asyncio
import json
from typing import AsyncGenerator, Callable, Optional
import boto3
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class TranscribeStreamService:
    """Manages real-time audio transcription via AWS Transcribe Streaming."""

    def __init__(self):
        self.client = boto3.client(
            "transcribe",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self._active_streams: dict = {}

    async def start_stream(
        self,
        interview_id: str,
        on_partial: Optional[Callable] = None,
        on_final: Optional[Callable] = None,
    ) -> str:
        """Start a transcription stream for an interview session."""
        stream_id = f"stream-{interview_id}"
        self._active_streams[stream_id] = {
            "buffer": [],
            "final_text": "",
            "is_active": True,
            "on_partial": on_partial,
            "on_final": on_final,
        }
        logger.info(f"Transcription stream started: {stream_id}")
        return stream_id

    async def feed_audio(self, stream_id: str, audio_chunk: bytes) -> Optional[str]:
        """Feed audio data to the transcription stream.

        In production this sends to AWS Transcribe Streaming API.
        For development, this simulates transcription processing.
        """
        stream = self._active_streams.get(stream_id)
        if not stream or not stream["is_active"]:
            return None

        stream["buffer"].append(audio_chunk)

        # In production: forward to AWS Transcribe Streaming
        # For dev: return accumulated buffer info
        return None

    async def process_transcript_result(
        self, stream_id: str, transcript_text: str, is_partial: bool = True
    ):
        """Process a transcript result from AWS Transcribe."""
        stream = self._active_streams.get(stream_id)
        if not stream:
            return

        if is_partial:
            if stream["on_partial"]:
                await stream["on_partial"](transcript_text)
        else:
            stream["final_text"] += " " + transcript_text
            if stream["on_final"]:
                await stream["on_final"](transcript_text)

    async def stop_stream(self, stream_id: str) -> str:
        """Stop a transcription stream and return final transcript."""
        stream = self._active_streams.get(stream_id)
        if not stream:
            return ""

        stream["is_active"] = False
        final_text = stream["final_text"].strip()
        del self._active_streams[stream_id]
        logger.info(f"Transcription stream stopped: {stream_id}")
        return final_text

    async def force_stop_after(self, stream_id: str, seconds: int) -> str:
        """Auto-close transcription stream after timeout (server-side timer)."""
        await asyncio.sleep(seconds)
        return await self.stop_stream(stream_id)


def get_transcribe_service() -> TranscribeStreamService:
    return TranscribeStreamService()
