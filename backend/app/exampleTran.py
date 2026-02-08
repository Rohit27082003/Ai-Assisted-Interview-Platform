import asyncio
from fastapi import FastAPI, WebSocket
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()


class WSHandler(TranscriptResultStreamHandler):
    def __init__(self, stream, websocket: WebSocket):
        super().__init__(stream)
        self.websocket = websocket

    async def handle_transcript_event(self, event: TranscriptEvent):
        for result in event.transcript.results:
            text = result.alternatives[0].transcript

            await self.websocket.send_json({
                "text": text,
                "final": not result.is_partial
            })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    client = TranscribeStreamingClient(region=os.getenv("AWS_REGION", "us-east-1"))

    stream = await client.start_stream_transcription(
        language_code="en-US",
        media_sample_rate_hz=16000,
        media_encoding="pcm",
    )

    handler = WSHandler(stream.output_stream, ws)

    async def send_audio():
        try:
            while True:
                audio = await ws.receive_bytes()
                await stream.input_stream.send_audio_event(audio_chunk=audio)
        except Exception:
            await stream.input_stream.end_stream()

    await asyncio.gather(
        send_audio(),
        handler.handle_events()
    )
