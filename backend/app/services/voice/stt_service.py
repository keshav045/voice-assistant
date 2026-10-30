"""Speech-to-Text (STT) service implementations."""

import io
import time
import logging
from typing import Optional
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.voice.base import AudioData, AudioFormat, BaseSTTService, TranscriptionResult

logger = logging.getLogger("nexus.voice.stt")


class OpenAIWhisperSTT(BaseSTTService):
    """OpenAI Whisper STT provider using AsyncOpenAI client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def transcribe(self, audio: AudioData) -> TranscriptionResult:
        if not self.client:
            logger.warning("OpenAI API key not set, falling back to mock STT")
            return await MockSTTService().transcribe(audio)

        start_time = time.perf_counter()
        extension = audio.format.value
        filename = f"audio.{extension}"

        # Wrap bytes in BytesIO with name attribute for multipart form upload
        audio_file = io.BytesIO(audio.data)
        audio_file.name = filename

        try:
            transcription = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
            )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            text = transcription.text.strip()
            language = getattr(transcription, "language", "en")

            return TranscriptionResult(
                text=text,
                language=language,
                confidence=1.0,
                latency_ms=latency_ms,
            )
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise


class MockSTTService(BaseSTTService):
    """Mock STT for testing, development, and offline mode."""

    async def transcribe(self, audio: AudioData) -> TranscriptionResult:
        start_time = time.perf_counter()
        # Simulated short processing delay
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return TranscriptionResult(
            text="Hello Nexus, how can you help me today?",
            language="en",
            confidence=0.98,
            latency_ms=latency_ms,
        )


def get_stt_service() -> BaseSTTService:
    """Factory to retrieve configured STT provider."""
    if settings.OPENAI_API_KEY:
        return OpenAIWhisperSTT()
    return MockSTTService()

