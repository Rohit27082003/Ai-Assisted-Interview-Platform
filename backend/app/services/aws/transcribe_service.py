"""AWS Transcribe streaming service for real-time speech-to-text."""

import asyncio
from typing import Optional, Callable, Dict, Any
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class InterviewEventHandler(TranscriptResultStreamHandler):
    """Handler for processing transcription events from AWS."""
    
    def __init__(self, output_stream, stream_state: Dict[str, Any]):
        super().__init__(output_stream)
        self.stream_state = stream_state

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        """Process a single transcript event."""
        results = transcript_event.transcript.results
        for result in results:
            if not result.alternatives:
                continue
            
            payload = result.alternatives[0]
            transcript = payload.transcript
            
            if result.is_partial:
                if self.stream_state["on_partial"]:
                    await self.stream_state["on_partial"](transcript)
            else:
                self.stream_state["final_text"] += " " + transcript
                if self.stream_state["on_final"]:
                    await self.stream_state["on_final"](transcript)


class TranscribeStreamService:
    """Manages real-time audio transcription via AWS Transcribe Streaming."""

    def __init__(self):
        self._active_streams: Dict[str, Dict[str, Any]] = {}

    async def start_stream(
        self,
        interview_id: str,
        on_partial: Optional[Callable] = None,
        on_final: Optional[Callable] = None,
    ) -> str:
        """Start a transcription stream for an interview session."""
        stream_id = f"stream-{interview_id}"
        queue = asyncio.Queue()
        
        self._active_streams[stream_id] = {
            "queue": queue,
            "final_text": "",
            "is_active": True,
            "on_partial": on_partial,
            "on_final": on_final,
        }
        
        # Start background processing task
        asyncio.create_task(self._process_stream(stream_id))
        
        logger.info(f"Transcription stream started: {stream_id}")
        return stream_id

    async def feed_audio(self, stream_id: str, audio_chunk: bytes) -> None:
        """Feed audio data to the transcription stream."""
        stream = self._active_streams.get(stream_id)
        if stream and stream["is_active"]:
            await stream["queue"].put(audio_chunk)

    async def stop_stream(self, stream_id: str) -> str:
        """Stop a transcription stream and return final transcript."""
        stream = self._active_streams.get(stream_id)
        if not stream:
            return ""

        stream["is_active"] = False
        # Signal EOF to generator
        await stream["queue"].put(None)
        
        # In a real scenario, we might want to wait for the processing task to finish 
        # via a completion event or similar. For now we return what we have.
        # Give a small buffer for final events to flush
        await asyncio.sleep(0.5) 
        
        final_text = stream["final_text"].strip()
        
        # Cleanup
        if stream_id in self._active_streams:
            del self._active_streams[stream_id]
            
        logger.info(f"Transcription stream stopped: {stream_id}")
        return final_text

    async def _process_stream(self, stream_id: str):
        """Internal background loop to send audio to AWS and handle results."""
        stream = self._active_streams.get(stream_id)
        if not stream:
            return

        client = TranscribeStreamingClient(
            region=settings.AWS_REGION,
        )

        async def audio_generator():
            while stream["is_active"]:
                chunk = await stream["queue"].get()
                if chunk is None:
                    break
                yield chunk

        try:
            # Note: We assume ogg-opus because frontend sends webm (which is usually opus). 
            # If this fails, consider 'pcm' or valid conversions.
            aws_stream = await client.start_stream_transcription(
                language_code="en-US",
                media_sample_rate_hz=48000, 
                media_encoding="ogg-opus",
            )
            
            handler = InterviewEventHandler(aws_stream.output_stream, stream)
            
            async def write_audio():
                async for chunk in audio_generator():
                    await aws_stream.input_stream.send_audio_event(audio_chunk=chunk)
                await aws_stream.input_stream.end_stream()

            await asyncio.gather(write_audio(), handler.handle_events())
            
        except Exception as e:
            logger.error(f"AWS Transcribe stream error for {stream_id}: {e}")
            # Ensure we mark stream as inactive so we don't leak
            stream["is_active"] = False

    async def force_stop_after(self, stream_id: str, seconds: int) -> str:
        """Auto-close transcription stream after timeout (server-side timer)."""
        await asyncio.sleep(seconds)
        return await self.stop_stream(stream_id)


def get_transcribe_service() -> TranscribeStreamService:
    return TranscribeStreamService()
