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
                    full_text = (self.stream_state["final_text"] + " " + transcript).strip()
                    await self.stream_state["on_partial"](full_text)
            else:
                self.stream_state["final_text"] += " " + transcript
                if self.stream_state["on_final"]:
                    await self.stream_state["on_final"](transcript)
                
                # Also trigger partial update with new final text to keep UI in sync
                if self.stream_state["on_partial"]:
                    await self.stream_state["on_partial"](self.stream_state["final_text"].strip())


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

    def is_active(self, stream_id: str) -> bool:
        """Check if a stream is currently active."""
        stream = self._active_streams.get(stream_id)
        return bool(stream and stream.get("is_active"))

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

        # If already inactive (e.g. error/timeout), return what we have
        if not stream["is_active"]:
            logger.info(f"Stream {stream_id} already inactive, returning partial text")
            return stream.get("final_text", "").strip()

        stream["is_active"] = False
        try:
            # Signal EOF
            if not stream["queue"].empty() or not stream["queue"].closed:
                 await stream["queue"].put(None)
        except Exception:
            pass
        
        # Wait briefly for processing to finish, but don't hang
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

        # Check AWS credentials
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            logger.error(f"AWS credentials not configured! Cannot start transcription for {stream_id}")
            stream["is_active"] = False
            return

        try:
            client = TranscribeStreamingClient(
                region=settings.AWS_REGION,
            )
        except Exception as e:
            logger.error(f"Failed to create TranscribeStreamingClient: {e}")
            stream["is_active"] = False
            return

        async def audio_generator():
            while stream["is_active"]:
                try:
                    chunk = await asyncio.wait_for(stream["queue"].get(), timeout=5.0)
                    if chunk is None:
                        break
                    yield chunk
                except asyncio.TimeoutError:
                    # No data for 5 seconds, continue waiting
                    continue
                except Exception as e:
                    logger.error(f"Audio generator error: {e}")
                    break

        try:
            # Use ogg-opus (AWS Transcribe supported format)
            # Browser WebRTC typically outputs webm, but AWS only accepts ogg-opus
            # The frontend should send audio as ogg-opus or we need conversion
            aws_stream = await client.start_stream_transcription(
                language_code=settings.TRANSCRIBE_LANGUAGE_CODE,
                media_sample_rate_hz=settings.TRANSCRIBE_SAMPLE_RATE,
                media_encoding="ogg-opus",  # AWS only supports: flac, g711-ulaw, g729, pcm, ogg-opus, g711-alaw
            )
            
            handler = InterviewEventHandler(aws_stream.output_stream, stream)
            
            async def write_audio():
                async for chunk in audio_generator():
                    await aws_stream.input_stream.send_audio_event(audio_chunk=chunk)
                await aws_stream.input_stream.end_stream()

            await asyncio.gather(write_audio(), handler.handle_events())

        except Exception as e:
            logger.error(f"AWS Transcribe stream error for {stream_id}: {e}", exc_info=True)
            # Ensure we mark stream as inactive so we don't leak
            stream["is_active"] = False

            # If transcription fails, we still want to preserve any partial text we got
            if stream.get("final_text"):
                logger.info(f"Preserved partial transcription for {stream_id}: {len(stream['final_text'])} chars")
        finally:
            # Clean up stream resources
            if stream_id in self._active_streams:
                logger.debug(f"Cleaning up stream resources for {stream_id}")

    async def force_stop_after(self, stream_id: str, seconds: int) -> str:
        """Auto-close transcription stream after timeout (server-side timer)."""
        await asyncio.sleep(seconds)
        return await self.stop_stream(stream_id)


# Singleton instance to maintain streams across requests
_transcribe_service: Optional[TranscribeStreamService] = None

def get_transcribe_service() -> TranscribeStreamService:
    """Get the global transcribe service instance (singleton)."""
    global _transcribe_service
    if _transcribe_service is None:
        _transcribe_service = TranscribeStreamService()
        logger.info("Initialized singleton TranscribeStreamService")
    return _transcribe_service
