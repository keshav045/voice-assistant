"""Modular STT -> LLM -> TTS Voice Pipeline."""

import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from app.services.voice.base import (
    AudioData,
    AudioFormat,
    BaseLLMVoiceService,
    BaseSTTService,
    BaseTTSService,
    VoiceTurnMetrics,
)
from app.services.voice.llm_voice_service import get_llm_voice_service
from app.services.voice.stt_service import get_stt_service
from app.services.voice.tts_service import get_tts_service

logger = logging.getLogger("nexus.voice.pipeline")


@dataclass
class VoiceTurnResult:
    """Complete result of a single conversational voice turn."""
    user_transcript: str
    assistant_text: str
    audio_bytes: bytes
    audio_format: AudioFormat
    metrics: VoiceTurnMetrics


class ModularVoicePipeline:
    """Orchestrates modular STT -> LLM -> TTS voice processing with latency profiling."""

    def __init__(
        self,
        stt_service: Optional[BaseSTTService] = None,
        llm_service: Optional[BaseLLMVoiceService] = None,
        tts_service: Optional[BaseTTSService] = None,
    ):
        self.stt = stt_service or get_stt_service()
        self.llm = llm_service or get_llm_voice_service()
        self.tts = tts_service or get_tts_service()

    async def process_audio_turn(
        self,
        audio: AudioData,
        conversation_history: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        voice: Optional[str] = "alloy",
    ) -> VoiceTurnResult:
        """Process spoken user audio and produce spoken assistant reply."""
        overall_start = time.perf_counter()

        # Step 1: STT
        stt_start = time.perf_counter()
        stt_result = await self.stt.transcribe(audio)
        stt_latency = round((time.perf_counter() - stt_start) * 1000, 2)
        logger.info(f"STT transcribed in {stt_latency}ms: '{stt_result.text}'")

        # Step 2: LLM
        messages = list(conversation_history)
        messages.append({"role": "user", "content": stt_result.text})

        llm_start = time.perf_counter()
        assistant_reply = await self.llm.generate_response(messages, system_prompt=system_prompt)
        llm_latency = round((time.perf_counter() - llm_start) * 1000, 2)
        logger.info(f"LLM generated in {llm_latency}ms: '{assistant_reply}'")

        # Step 3: TTS
        tts_start = time.perf_counter()
        synthesis = await self.tts.synthesize(assistant_reply, voice=voice)
        tts_latency = round((time.perf_counter() - tts_start) * 1000, 2)
        logger.info(f"TTS synthesized in {tts_latency}ms ({synthesis.character_count} chars)")

        total_latency = round((time.perf_counter() - overall_start) * 1000, 2)

        metrics = VoiceTurnMetrics(
            stt_latency_ms=stt_latency,
            llm_latency_ms=llm_latency,
            tts_latency_ms=tts_latency,
            total_latency_ms=total_latency,
            user_transcript_chars=len(stt_result.text),
            assistant_response_chars=len(assistant_reply),
        )

        return VoiceTurnResult(
            user_transcript=stt_result.text,
            assistant_text=assistant_reply,
            audio_bytes=synthesis.audio_bytes,
            audio_format=synthesis.format,
            metrics=metrics,
        )

    async def process_text_turn(
        self,
        text: str,
        conversation_history: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        voice: Optional[str] = "alloy",
    ) -> VoiceTurnResult:
        """Process incoming text and generate spoken audio output."""
        overall_start = time.perf_counter()

        messages = list(conversation_history)
        messages.append({"role": "user", "content": text})

        llm_start = time.perf_counter()
        assistant_reply = await self.llm.generate_response(messages, system_prompt=system_prompt)
        llm_latency = round((time.perf_counter() - llm_start) * 1000, 2)

        tts_start = time.perf_counter()
        synthesis = await self.tts.synthesize(assistant_reply, voice=voice)
        tts_latency = round((time.perf_counter() - tts_start) * 1000, 2)

        total_latency = round((time.perf_counter() - overall_start) * 1000, 2)

        metrics = VoiceTurnMetrics(
            stt_latency_ms=0.0,
            llm_latency_ms=llm_latency,
            tts_latency_ms=tts_latency,
            total_latency_ms=total_latency,
            user_transcript_chars=len(text),
            assistant_response_chars=len(assistant_reply),
        )

        return VoiceTurnResult(
            user_transcript=text,
            assistant_text=assistant_reply,
            audio_bytes=synthesis.audio_bytes,
            audio_format=synthesis.format,
            metrics=metrics,
        )

