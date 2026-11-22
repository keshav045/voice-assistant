"""Local STT & TTS Pipeline for Nexus AI Assistant.

Provides 100% offline and free speech capabilities:
1. LocalWhisperSTT: Speech-to-Text powered by faster-whisper (tiny.en / base.en).
2. LocalEdgeTTS: High-fidelity neural TTS powered by edge-tts (no API keys required).
3. Standalone helper functions for synchronous audio transcription and synthesis.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from typing import Optional

from livekit.agents import stt, tts, APIConnectOptions
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.rtc import AudioFrame

from agent.voice import clean_spoken_text

logger = logging.getLogger("nexus.local_voice")

_GLOBAL_WHISPER_MODEL = None


def _get_whisper_model(model_size: str = "tiny.en"):
    """Lazily load and cache the faster-whisper model on CPU."""
    global _GLOBAL_WHISPER_MODEL
    if _GLOBAL_WHISPER_MODEL is None:
        try:
            from faster_whisper import WhisperModel
            _GLOBAL_WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info(f"Loaded faster-whisper model: {model_size}")
        except Exception as e:
            logger.error(f"Failed to load faster-whisper model: {e}")
            return None
    return _GLOBAL_WHISPER_MODEL


class LocalWhisperSTT(stt.STT):
    """Local Speech-to-Text adapter compatible with LiveKit Agents."""

    def __init__(self, model_size: str = "tiny.en"):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False),
        )
        self._model_size = model_size
        # Warm the model
        _get_whisper_model(self._model_size)

    async def _recognize_impl(
        self,
        buffer: AudioFrame,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> stt.SpeechEvent:
        """Transcribe an AudioFrame into text using local faster-whisper."""
        try:
            wav_bytes = buffer.to_wav_bytes()
            model = _get_whisper_model(self._model_size)
            if not model:
                return stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[stt.SpeechData(text="", language="en")],
                )

            def _run_transcription():
                segments, _ = model.transcribe(io.BytesIO(wav_bytes), beam_size=1)
                return "".join(s.text for s in segments).strip()

            text = await asyncio.to_thread(_run_transcription)
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(text=text, language="en")],
            )
        except Exception as e:
            logger.error(f"LocalWhisperSTT recognition error: {e}")
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(text="", language="en")],
            )


class LocalEdgeTTS(tts.TTS):
    """Free, high-fidelity neural Text-to-Speech adapter compatible with LiveKit Agents."""

    def __init__(self, voice: str = "en-US-ChristopherNeural"):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=24000,
            num_channels=1,
        )
        self._voice = voice

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> tts.ChunkedStream:
        return EdgeChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class EdgeChunkedStream(tts.ChunkedStream):
    """Stream synthesis chunks from edge-tts to LiveKit audio emitter."""

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        clean = clean_spoken_text(self.input_text)
        if not clean:
            return

        try:
            import edge_tts

            output_emitter.initialize(
                request_id=uuid.uuid4().hex,
                sample_rate=24000,
                num_channels=1,
                mime_type="audio/mp3",
            )
            communicate = edge_tts.Communicate(clean, self._tts._voice)
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    output_emitter.push(chunk["data"])
            output_emitter.flush()
        except Exception as e:
            logger.error(f"EdgeChunkedStream synthesis error: {e}")


def transcribe_audio_local(audio_bytes: bytes, model_size: str = "tiny.en") -> str:
    """Synchronous helper to transcribe audio bytes using local faster-whisper."""
    if not audio_bytes or len(audio_bytes) < 100:
        return ""
    try:
        model = _get_whisper_model(model_size)
        if not model:
            return ""
        segments, _ = model.transcribe(io.BytesIO(audio_bytes), beam_size=1)
        return "".join(s.text for s in segments).strip()
    except Exception as e:
        logger.error(f"transcribe_audio_local error: {e}")
        return ""


def synthesize_speech_local(text: str, voice: str = "en-US-ChristopherNeural") -> bytes:
    """Synchronous helper to synthesize speech using free neural edge-tts."""
    clean = clean_spoken_text(text)
    if not clean:
        return b""

    try:
        import edge_tts

        async def _synth():
            communicate = edge_tts.Communicate(clean, voice)
            chunks = []
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(lambda: asyncio.run(_synth())).result()
            else:
                return loop.run_until_complete(_synth())
        except Exception:
            return asyncio.run(_synth())
    except Exception as e:
        logger.error(f"synthesize_speech_local error: {e}")
        return b""
