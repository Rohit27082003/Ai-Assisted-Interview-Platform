"""AWS Transcribe streaming service for real-time speech-to-text."""

import asyncio
import shutil
import time
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

    # Don't retry a failed stream for this many seconds
    FAILURE_COOLDOWN_SECONDS = 30

    def __init__(self):
        self._active_streams: Dict[str, Dict[str, Any]] = {}
        self._failed_streams: Dict[str, float] = {}  # stream_id → failure timestamp

    async def start_stream(
        self,
        interview_id: str,
        on_partial: Optional[Callable] = None,
        on_final: Optional[Callable] = None,
        media_format: str = "ogg-opus",
    ) -> str:
        """Start a transcription stream for an interview session.

        Args:
            media_format: Audio format from frontend — "ogg-opus" (Firefox) or "webm-opus" (Chrome/Edge).
                          When webm-opus, audio is remuxed to ogg-opus via ffmpeg before sending to AWS.
        """
        stream_id = f"stream-{interview_id}"

        # Prevent spam: don't retry if the stream failed recently
        failed_at = self._failed_streams.get(stream_id)
        if failed_at and (time.monotonic() - failed_at) < self.FAILURE_COOLDOWN_SECONDS:
            return stream_id

        queue = asyncio.Queue()

        self._active_streams[stream_id] = {
            "queue": queue,
            "final_text": "",
            "is_active": True,
            "on_partial": on_partial,
            "on_final": on_final,
            "media_format": media_format,
        }

        # Start background processing task
        asyncio.create_task(self._process_stream(stream_id))

        logger.info(f"Transcription stream started: {stream_id} (format={media_format})")
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
            # Signal EOF to the audio generator
            await stream["queue"].put(None)
        except Exception:
            pass

        # Wait briefly for processing to finish, but don't hang
        await asyncio.sleep(0.5)

        final_text = stream["final_text"].strip()

        # Cleanup
        if stream_id in self._active_streams:
            del self._active_streams[stream_id]
        self._failed_streams.pop(stream_id, None)

        logger.info(f"Transcription stream stopped: {stream_id}")
        return final_text

    async def _process_stream(self, stream_id: str):
        """Internal background loop to send audio to AWS and handle results."""
        stream = self._active_streams.get(stream_id)
        if not stream:
            return

        try:
            # TranscribeStreamingClient uses the standard AWS credential chain
            # (env vars AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, already loaded
            # from .env by load_dotenv() in config.py)
            client = TranscribeStreamingClient(region=settings.AWS_REGION)
        except Exception as e:
            logger.error(f"Failed to create TranscribeStreamingClient: {e}")
            stream["is_active"] = False
            self._failed_streams[stream_id] = time.monotonic()
            return

        media_format = stream.get("media_format", "ogg-opus")
        needs_conversion = media_format == "webm-opus"
        ffmpeg_proc = None

        if needs_conversion:
            ffmpeg_proc = await self._start_ffmpeg_converter(stream_id)
            if not ffmpeg_proc:
                logger.warning(f"ffmpeg not available — webm-opus transcription disabled for {stream_id}")
                stream["is_active"] = False
                self._failed_streams[stream_id] = time.monotonic()
                return

        async def audio_generator():
            """Yield audio chunks, converting webm→ogg via ffmpeg if needed."""
            if needs_conversion and ffmpeg_proc:
                # Read converted ogg data from ffmpeg stdout
                while stream["is_active"]:
                    try:
                        data = await asyncio.wait_for(ffmpeg_proc.stdout.read(4096), timeout=5.0)
                        if not data:
                            break
                        yield data
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"ffmpeg read error: {e}")
                        break
            else:
                # Direct ogg-opus: pass through without conversion
                while stream["is_active"]:
                    try:
                        chunk = await asyncio.wait_for(stream["queue"].get(), timeout=5.0)
                        if chunk is None:
                            break
                        yield chunk
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Audio generator error: {e}")
                        break

        # If converting, start a task to feed raw webm chunks into ffmpeg stdin
        feeder_task = None
        if needs_conversion and ffmpeg_proc:
            feeder_task = asyncio.create_task(
                self._feed_ffmpeg(stream, ffmpeg_proc)
            )

        try:
            aws_stream = await client.start_stream_transcription(
                language_code=settings.TRANSCRIBE_LANGUAGE_CODE,
                media_sample_rate_hz=settings.TRANSCRIBE_SAMPLE_RATE,
                media_encoding="ogg-opus",
            )

            handler = InterviewEventHandler(aws_stream.output_stream, stream)

            async def write_audio():
                async for chunk in audio_generator():
                    await aws_stream.input_stream.send_audio_event(audio_chunk=chunk)
                await aws_stream.input_stream.end_stream()

            await asyncio.gather(write_audio(), handler.handle_events())

        except Exception as e:
            logger.error(f"AWS Transcribe stream error for {stream_id}: {e}", exc_info=True)
            stream["is_active"] = False
            self._failed_streams[stream_id] = time.monotonic()

            if stream.get("final_text"):
                logger.info(f"Preserved partial transcription for {stream_id}: {len(stream['final_text'])} chars")
        finally:
            if feeder_task and not feeder_task.done():
                feeder_task.cancel()
            if ffmpeg_proc:
                try:
                    ffmpeg_proc.kill()
                    await ffmpeg_proc.wait()
                except Exception:
                    pass
            if stream_id in self._active_streams:
                logger.debug(f"Cleaning up stream resources for {stream_id}")

    async def _start_ffmpeg_converter(self, stream_id: str):
        """Start an ffmpeg subprocess that remuxes webm-opus → ogg-opus."""
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            logger.error(f"ffmpeg not found in PATH — cannot convert webm to ogg for {stream_id}")
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg_path,
                "-f", "webm",
                "-i", "pipe:0",
                "-f", "ogg",
                "-c:a", "copy",   # Remux only — no re-encoding
                "-y", "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info(f"Started ffmpeg webm→ogg converter for {stream_id} (pid={proc.pid})")
            return proc
        except Exception as e:
            logger.error(f"Failed to start ffmpeg for {stream_id}: {e}")
            return None

    async def _feed_ffmpeg(self, stream: Dict[str, Any], proc) -> None:
        """Feed raw webm audio chunks from the queue into ffmpeg stdin."""
        try:
            while stream["is_active"]:
                try:
                    chunk = await asyncio.wait_for(stream["queue"].get(), timeout=5.0)
                    if chunk is None:
                        break
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"ffmpeg feed error: {e}")
                    break
        finally:
            try:
                proc.stdin.close()
                await proc.stdin.wait_closed()
            except Exception:
                pass

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
