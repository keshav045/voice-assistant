"""Abstract base classes and data transfer objects for Voice services."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"
    PCM16 = "pcm16"
    WEBM = "webm"
    OGG = "ogg"


@dataclass
class AudioData:
    """Raw audio payload with formatting metadata."""
    data: bytes
    format: AudioFormat = AudioFormat.WEBM
    sample_rate: int = 24000
    channels: int = 1


@dataclass
class TranscriptionResult:
    """Result of speech-to-text recognition."""
    text: str
    language: Optional[str] = "en"
    confidence: float = 1.0
    latency_ms: float = 0.0


@dataclass
class SynthesisResult:
    """Result of text-to-speech synthesis."""
    audio_bytes: bytes
    format: AudioFormat = AudioFormat.MP3
    latency_ms: float = 0.0
    character_count: int = 0


@dataclass
class VoiceTurnMetrics:
    """Latency and timing metrics for a conversation turn."""
    stt_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    tts_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    user_transcript_chars: int = 0
    assistant_response_chars: int = 0


class BaseSTTService(ABC):
    """Abstract interface for Speech-to-Text services."""

    @abstractmethod
    async def transcribe(self, audio: AudioData) -> TranscriptionResult:
        """Transcribe audio into text."""
        pass


class BaseTTSService(ABC):
    """Abstract interface for Text-to-Speech services."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Synthesize text into spoken audio."""
        pass


class BaseLLMVoiceService(ABC):
    """Abstract interface for conversational LLM generation."""

    @abstractmethod
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate conversational assistant response."""
        pass

