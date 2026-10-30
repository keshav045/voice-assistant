"""OpenAI Realtime API Speech-to-Speech service bridge."""

import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional
import websockets
from app.core.config import settings

logger = logging.getLogger("nexus.voice.realtime")

OPENAI_REALTIME_WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"


class RealtimeVoiceBridge:
    """Relays bidirectional audio events to and from OpenAI Realtime API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.openai_ws = None

    async def connect(self) -> bool:
        """Establish outbound WebSocket to OpenAI Realtime endpoint."""
        if not self.api_key:
            logger.warning("No OpenAI API key provided for Realtime API bridge.")
            return False

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        try:
            self.openai_ws = await websockets.connect(
                OPENAI_REALTIME_WS_URL,
                extra_headers=headers,
            )
            # Send initial session configuration
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": "You are Nexus, an agentic voice productivity assistant. Keep voice replies concise and natural.",
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                    },
                },
            }
            await self.openai_ws.send(json.dumps(session_update))
            logger.info("Connected to OpenAI Realtime API.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            return False

    async def send_audio_chunk(self, base64_pcm16: str) -> None:
        """Stream an input audio chunk to OpenAI Realtime."""
        if not self.openai_ws:
            return
        event = {
            "type": "input_audio_buffer.append",
            "audio": base64_pcm16,
        }
        await self.openai_ws.send(json.dumps(event))

    async def commit_audio_buffer(self) -> None:
        """Signal end of user turn."""
        if not self.openai_ws:
            return
        await self.openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await self.openai_ws.send(json.dumps({"type": "response.create"}))

    async def receive_events(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Yield events received from OpenAI Realtime API."""
        if not self.openai_ws:
            return
        try:
            async for raw_message in self.openai_ws:
                event = json.loads(raw_message)
                yield event
        except websockets.ConnectionClosed:
            logger.info("OpenAI Realtime connection closed.")
        except Exception as e:
            logger.error(f"Error receiving from OpenAI Realtime: {e}")

    async def close(self) -> None:
        """Gracefully close the Realtime connection."""
        if self.openai_ws:
            await self.openai_ws.close()
            self.openai_ws = None
