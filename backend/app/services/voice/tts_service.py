"""Text-to-Speech (TTS) service implementations."""

import time
import logging
from typing import Optional
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.voice.base import AudioFormat, BaseTTSService, SynthesisResult

logger = logging.getLogger("nexus.voice.tts")


class OpenAITTSService(BaseTTSService):
    """OpenAI TTS provider using tts-1 or tts-1-hd."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = "alloy",
        speed: float = 1.0,
    ) -> SynthesisResult:
        if not self.client:
            logger.warning("OpenAI API key not set, falling back to mock TTS")
            return await MockTTSService().synthesize(text, voice, speed)

        start_time = time.perf_counter()
        try:
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice=voice or "alloy",
                input=text,
                speed=speed,
                response_format="mp3",
            )
            audio_bytes = await response.aread()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            return SynthesisResult(
                audio_bytes=audio_bytes,
                format=AudioFormat.MP3,
                latency_ms=latency_ms,
                character_count=len(text),
            )
        except Exception as e:
            logger.error(f"OpenAI TTS synthesis failed: {e}")
            raise


class MockTTSService(BaseTTSService):
    """Mock TTS returning a valid minimalist audio header for testing."""

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = "alloy",
        speed: float = 1.0,
    ) -> SynthesisResult:
        start_time = time.perf_counter()
        # Minimalist valid WAV header (44 bytes standard PCM WAV)
        wav_header = bytes([
            0x52, 0x49, 0x46, 0x46,  # "RIFF"
            0x24, 0x00, 0x00, 0x00,  # ChunkSize (36 + SubChunk2Size)
            0x57, 0x41, 0x56, 0x45,  # "WAVE"
            0x66, 0x6D, 0x74, 0x20,  # "fmt "
            0x10, 0x00, 0x00, 0x00,  # Subchunk1Size (16 for PCM)
            0x01, 0x00,              # AudioFormat (1 = PCM)
            0x01, 0x00,              # NumChannels (1 = Mono)
            0x44, 0xAC, 0x00, 0x00,  # SampleRate (44100)
            0x88, 0x58, 0x01, 0x00,  # ByteRate (44100 * 1 * 16/8 = 88200)
            0x02, 0x00,              # BlockAlign (1 * 16/8 = 2)
            0x10, 0x00,              # BitsPerSample (16)
            0x64, 0x61, 0x74, 0x61,  # "data"
            0x00, 0x00, 0x00, 0x00   # Subchunk2Size (0 bytes of data)
        ])
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return SynthesisResult(
            audio_bytes=wav_header,
            format=AudioFormat.WAV,
            latency_ms=latency_ms,
            character_count=len(text),
        )


def get_tts_service() -> BaseTTSService:
    """Factory to retrieve configured TTS provider."""
    if settings.OPENAI_API_KEY:
        return OpenAITTSService()
    return MockTTSService()

