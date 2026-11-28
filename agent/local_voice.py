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
import math
import os
from pathlib import Path
import re
import sys
import sysconfig
import threading
import time
import uuid
import wave
from typing import Any, Optional

import numpy as np
from livekit.agents import stt, tts, APIConnectOptions
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.rtc import AudioFrame

from agent.voice import clean_spoken_text

logger = logging.getLogger("nexus.local_voice")

_WHISPER_LOCK = threading.Lock()
_WHISPER_MODELS: dict[tuple[str, str, str, int], Any] = {}
_CUDA_DLL_HANDLES: list[Any] = []
_CUDA_DLL_DIRS_REGISTERED: set[str] = set()
_TARGET_SAMPLE_RATE = 16000
_UNSET = object()
_DEFAULT_STT_PROMPT = (
    "Nexus AI assistant, WhatsApp, YouTube, Gmail, "
    "Paracetamol, Dolo 650, Ibuprofen."
)


def is_strict_local_mode() -> bool:
    """Return True when STRICT_LOCAL_MODE enforces zero cloud STT/TTS network calls."""
    return os.environ.get("STRICT_LOCAL_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _stt_language(explicit_language: Optional[str] = None) -> Optional[str]:
    """Resolve STT language from explicit override or STT_LANGUAGE (default 'en')."""
    if explicit_language is not None and str(explicit_language).strip():
        v = str(explicit_language).strip().lower()
    else:
        v = os.environ.get("STT_LANGUAGE", "en").strip().lower()
    return None if v in {"", "auto", "none"} else v


def _stt_model_size(explicit_size: Optional[str] = None) -> str:
    """Resolve Whisper model size from explicit override or WHISPER_MODEL_SIZE (default 'base.en')."""
    if explicit_size is not None and str(explicit_size).strip():
        return str(explicit_size).strip()
    return os.environ.get("WHISPER_MODEL_SIZE", "base.en").strip() or "base.en"


def _stt_beam(explicit_beam: Optional[int] = None) -> int:
    """Resolve faster-whisper beam size from explicit arg or WHISPER_BEAM_SIZE (default 1)."""
    if explicit_beam is not None:
        return max(1, min(10, int(explicit_beam)))
    try:
        return max(1, min(10, int(os.environ.get("WHISPER_BEAM_SIZE", "1").strip() or "1")))
    except ValueError:
        return 1


def _stt_cpu_threads(explicit_threads: Optional[int] = None) -> int:
    """Resolve faster-whisper CPU thread count from explicit arg or WHISPER_CPU_THREADS."""
    if explicit_threads is not None:
        return max(1, int(explicit_threads))
    raw = os.environ.get("WHISPER_CPU_THREADS", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return min(4, max(2, os.cpu_count() or 4))


def _stt_vad_filter(explicit_vad_filter: Optional[bool] = None) -> bool:
    """Resolve faster-whisper internal vad_filter from explicit arg or WHISPER_VAD_FILTER (default True)."""
    if explicit_vad_filter is not None:
        return bool(explicit_vad_filter)
    raw = os.environ.get("WHISPER_VAD_FILTER", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return True


def _stt_device() -> str:
    """Resolve faster-whisper execution device from STT_DEVICE (default 'cpu')."""
    dev = os.environ.get("STT_DEVICE", "cpu").strip().lower()
    return dev if dev in {"cpu", "cuda", "auto"} else "cpu"


def _stt_compute_type(device: str) -> str:
    """Resolve CTranslate2 compute type for cpu ('int8') or cuda ('int8_float16')."""
    override = os.environ.get("STT_COMPUTE_TYPE", "").strip()
    if override:
        return override
    return "int8_float16" if device == "cuda" else "int8"


def _stt_initial_prompt() -> Optional[str]:
    """Return optional domain vocabulary prompt only when explicitly set in STT_INITIAL_PROMPT."""
    val = os.environ.get("STT_INITIAL_PROMPT", "").strip()
    if not val or val.lower() in {"none", "off", "false"}:
        return None
    return val


def _is_repetitive_hallucination(text: str) -> bool:
    """Detect Whisper decoder stutter loops (e.g., repeated words/phrases or '-2-2-2-2-2')."""
    clean = (text or "").strip()
    if not clean:
        return False
    if re.search(r"(?:^|[\s,])([a-zA-Z0-9']+)(?:[\s,;:\-]+\1){3,}(?:\b|$)", clean, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(\w+\s+\w+)\b(?:[\s,;:\-]+\1){2,}", clean, flags=re.IGNORECASE):
        return True
    if re.search(r"(?:-\d){5,}", clean):
        return True
    return False


def _extract_valid_whisper_text(segments: Any) -> str:
    """Keep coherent Whisper segments while rejecting low-confidence noise and compression loops."""
    valid_parts: list[str] = []
    for seg in segments:
        txt = (getattr(seg, "text", "") or "").strip()
        if not txt:
            continue
        comp_ratio = getattr(seg, "compression_ratio", None)
        avg_logprob = getattr(seg, "avg_logprob", None)
        no_speech_prob = getattr(seg, "no_speech_prob", None)

        if isinstance(comp_ratio, (int, float)) and comp_ratio > 2.2:
            logger.debug(f"Filtered Whisper compression loop ({comp_ratio:.2f}): {txt[:60]!r}")
            continue
        if isinstance(avg_logprob, (int, float)) and avg_logprob < -0.98:
            logger.debug(f"Filtered low-logprob Whisper hallucination ({avg_logprob:.2f}): {txt[:60]!r}")
            continue
        if (
            isinstance(avg_logprob, (int, float))
            and isinstance(no_speech_prob, (int, float))
            and ((avg_logprob < -0.88 and no_speech_prob > 0.25) or (no_speech_prob > 0.70 and avg_logprob < -0.60))
        ):
            logger.debug(f"Filtered noisy Whisper segment (logprob={avg_logprob:.2f}, no_speech={no_speech_prob:.2f}): {txt[:60]!r}")
            continue
        if _is_repetitive_hallucination(txt):
            logger.debug(f"Filtered repetitive Whisper hallucination: {txt[:60]!r}")
            continue
        valid_parts.append(txt)

    joined = " ".join(valid_parts).strip()
    if _is_repetitive_hallucination(joined):
        return ""
    return joined


def _decode_audio_to_16k_float32(audio_bytes: bytes) -> np.ndarray:
    """Decode WAV or compressed audio bytes to a mono 16kHz float32 array without PyAV metadata_errors."""
    if audio_bytes[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())

            if sampwidth == 1:
                audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            elif sampwidth == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 4:
                audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                raise ValueError(f"Unsupported WAV sample width: {sampwidth}")

            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)

            if sample_rate != _TARGET_SAMPLE_RATE and len(audio) > 0:
                from scipy.signal import resample_poly
                divisor = math.gcd(_TARGET_SAMPLE_RATE, sample_rate)
                audio = resample_poly(audio, _TARGET_SAMPLE_RATE // divisor, sample_rate // divisor).astype(np.float32)

            return np.ascontiguousarray(audio, dtype=np.float32)
        except (wave.Error, ValueError):
            pass

    # Fallback for non-PCM / compressed formats (e.g. webm, mp3, ogg) using PyAV >= 19 compatible open()
    import av

    resampler = av.audio.resampler.AudioResampler(
        format="s16",
        layout="mono",
        rate=_TARGET_SAMPLE_RATE,
    )
    chunks = []
    with av.open(io.BytesIO(audio_bytes), mode="r") as container:
        for frame in container.decode(audio=0):
            frame.pts = None
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().reshape(-1))
        for resampled in resampler.resample(None):
            chunks.append(resampled.to_ndarray().reshape(-1))

    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return (np.concatenate(chunks).astype(np.float32) / 32768.0)


def _transcribe_audio_bytes(
    audio_bytes: bytes,
    model_size: Optional[str] = None,
    language: Optional[str] = None,
    *,
    beam_size: Optional[int] = None,
    cpu_threads: Optional[int] = None,
    vad_filter: Optional[bool] = None,
    initial_prompt: Any = _UNSET,
) -> str:
    """Decode audio bytes and transcribe them with the cached faster-whisper model."""
    if not audio_bytes or len(audio_bytes) < 44:
        return ""
    size_key = _stt_model_size(model_size)
    device = _stt_device()
    threads = _stt_cpu_threads(cpu_threads)
    model = _get_whisper_model(size_key, device=device, cpu_threads=threads)
    if not model:
        return ""
    audio = _decode_audio_to_16k_float32(audio_bytes)
    if audio.size == 0:
        return ""
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    # Skip silent or ultra-low noise frames before running decoder passes
    if peak < 0.008 or rms < 0.0015:
        return ""
    if 0.015 <= peak < 0.35 and rms >= 0.003:
        gain = min(4.0, 0.45 / peak)
        audio = np.clip(audio * gain, -0.95, 0.95).astype(np.float32)

    stt_lang = _stt_language(language)
    beam = _stt_beam(beam_size)
    use_vad = _stt_vad_filter(vad_filter)
    prompt = _stt_initial_prompt() if initial_prompt is _UNSET else (initial_prompt or None)
    tx_kwargs: dict[str, Any] = {
        "beam_size": beam,
        "best_of": 1,
        "language": stt_lang,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "without_timestamps": True,
        "vad_filter": use_vad,
        "no_speech_threshold": 0.6,
        "log_prob_threshold": -0.95,
        "compression_ratio_threshold": 2.2,
    }
    if use_vad:
        tx_kwargs["vad_parameters"] = {"min_silence_duration_ms": 300}
    if prompt:
        tx_kwargs["initial_prompt"] = prompt

    try:
        segments, _ = model.transcribe(audio, **tx_kwargs)
        return _extract_valid_whisper_text(segments)
    except Exception as exc:
        if device != "cpu":
            logger.warning(f"CUDA transcribe failed ({exc}); falling back to CPU INT8 for '{size_key}'.")
            cpu_model = _get_whisper_model(size_key, device="cpu", compute_type="int8", cpu_threads=threads)
            if cpu_model is not None:
                segments, _ = cpu_model.transcribe(audio, **tx_kwargs)
                return _extract_valid_whisper_text(segments)
        raise


def _register_cuda_dll_paths() -> list[str]:
    """Register nvidia-* wheel DLL directories via os.add_dll_directory when STT_DEVICE=cuda."""
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return []
    registered: list[str] = []
    candidates: list[Path] = []
    for root in {Path(sys.prefix) / "Lib" / "site-packages", Path(sysconfig.get_path("purelib") or "")}:
        nvidia_dir = root / "nvidia"
        if nvidia_dir.is_dir():
            for pkg_name in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
                bin_dir = nvidia_dir / pkg_name / "bin"
                if bin_dir.is_dir():
                    candidates.append(bin_dir)
    for d in candidates:
        key = str(d.resolve())
        if key not in _CUDA_DLL_DIRS_REGISTERED:
            try:
                _CUDA_DLL_HANDLES.append(os.add_dll_directory(key))
                _CUDA_DLL_DIRS_REGISTERED.add(key)
                registered.append(key)
            except OSError:
                pass
    return registered


def _load_whisper_instance(size_key: str, device: str, compute_type: str, cpu_threads: int):
    """Instantiate WhisperModel preferring cached local files before network download."""
    if device == "cuda":
        _register_cuda_dll_paths()
    from faster_whisper import WhisperModel

    kwargs: dict[str, Any] = {
        "device": device,
        "compute_type": compute_type,
        "cpu_threads": cpu_threads,
    }
    try:
        return WhisperModel(size_key, local_files_only=True, **kwargs)
    except Exception:
        return WhisperModel(size_key, **kwargs)


def prewarm_stt_decode(model_size: Optional[str] = None, duration_s: float = 1.0) -> float:
    """Run a 1-second low-amplitude warm-up decode so CTranslate2 and VAD kernels init before Turn 1."""
    samples = max(1600, int(_TARGET_SAMPLE_RATE * max(0.5, duration_s)))
    t = np.arange(samples, dtype=np.float32) / float(_TARGET_SAMPLE_RATE)
    pcm16 = (0.02 * np.sin(2.0 * math.pi * 220.0 * t) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_TARGET_SAMPLE_RATE)
        wf.writeframes(pcm16.tobytes())
    t0 = time.perf_counter()
    _transcribe_audio_bytes(buf.getvalue(), model_size=model_size)
    return round((time.perf_counter() - t0) * 1000.0, 1)


def _get_whisper_model(
    model_size: Optional[str] = None,
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    cpu_threads: Optional[int] = None,
):
    """Lazily load and cache a faster-whisper model (defaults to CPU INT8)."""
    size_key = _stt_model_size(model_size)
    dev = (device or _stt_device()).strip().lower()
    if dev == "auto":
        dev = "cpu"
    ctype = (compute_type or _stt_compute_type(dev)).strip()
    threads = _stt_cpu_threads(cpu_threads)
    cache_key = (size_key, dev, ctype, threads)
    if cache_key in _WHISPER_MODELS:
        return _WHISPER_MODELS[cache_key]

    with _WHISPER_LOCK:
        if cache_key in _WHISPER_MODELS:
            return _WHISPER_MODELS[cache_key]
        try:
            model = _load_whisper_instance(size_key, dev, ctype, threads)
            _WHISPER_MODELS[cache_key] = model
            logger.info(f"Loaded faster-whisper model: {size_key} (device={dev}, compute={ctype}, threads={threads})")
            return model
        except Exception as e:
            if dev != "cpu":
                logger.warning(f"Failed loading Whisper on {dev} ({e}); falling back to CPU INT8.")
                try:
                    cpu_key = (size_key, "cpu", "int8", threads)
                    if cpu_key in _WHISPER_MODELS:
                        return _WHISPER_MODELS[cpu_key]
                    cpu_model = _load_whisper_instance(size_key, "cpu", "int8", threads)
                    _WHISPER_MODELS[cpu_key] = cpu_model
                    return cpu_model
                except Exception as cpu_err:
                    logger.error(f"Failed to load faster-whisper CPU fallback: {cpu_err}")
                    return None
            logger.error(f"Failed to load faster-whisper model: {e}")
            return None


class LocalWhisperSTT(stt.STT):
    """Local Speech-to-Text adapter compatible with LiveKit Agents."""

    def __init__(self, model_size: Optional[str] = None):
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=False, interim_results=False),
        )
        self._model_size = _stt_model_size(model_size)
        _get_whisper_model(self._model_size)

    async def _recognize_impl(
        self,
        buffer: AudioFrame,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> stt.SpeechEvent:
        """Transcribe an AudioFrame into text using local faster-whisper."""
        explicit_lang = language if (language is not NOT_GIVEN and isinstance(language, str)) else None
        resolved_lang = _stt_language(explicit_lang) or "auto"
        try:
            wav_bytes = buffer.to_wav_bytes()
            text = await asyncio.to_thread(_transcribe_audio_bytes, wav_bytes, self._model_size, explicit_lang)
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(text=text, language=resolved_lang)],
            )
        except Exception as e:
            logger.error(f"LocalWhisperSTT recognition error: {e}")
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(text="", language=resolved_lang)],
            )

_PIPER_LOCK = threading.Lock()
_PIPER_VOICES: dict[str, Any] = {}


def _resolve_piper_model_path(voice_name: str | None = None) -> Path:
    """Resolve local Piper ONNX model path from PIPER_MODEL_PATH or workspace models/piper."""
    override = os.environ.get("PIPER_MODEL_PATH", "").strip()
    if override:
        return Path(override)
    chosen = (voice_name or os.environ.get("PIPER_VOICE", "en_US-lessac-medium")).strip() or "en_US-lessac-medium"
    if chosen.endswith(".onnx"):
        return Path(chosen)
    return Path(__file__).resolve().parent.parent / "models" / "piper" / f"{chosen}.onnx"


def _get_piper_voice(voice_name: str | None = None):
    """Load, cache, and warmup offline Piper neural TTS voice (CPU/ONNX, zero network calls)."""
    chosen = (voice_name or os.environ.get("PIPER_VOICE", "en_US-lessac-medium")).strip() or "en_US-lessac-medium"
    if chosen in _PIPER_VOICES:
        return _PIPER_VOICES[chosen]

    with _PIPER_LOCK:
        if chosen in _PIPER_VOICES:
            return _PIPER_VOICES[chosen]
        model_path = _resolve_piper_model_path(chosen)
        if not model_path.exists():
            return None
        try:
            from piper import PiperVoice

            voice = PiperVoice.load(str(model_path))
            # Prewarm ONNX Runtime session once so the first live turn hits ~150-300ms latency.
            for _ in voice.synthesize("Ready."):
                pass
            _PIPER_VOICES[chosen] = voice
            logger.info(f"Preloaded offline Piper TTS voice: {model_path.name} ({voice.config.sample_rate}Hz)")
            return voice
        except Exception as exc:
            logger.warning(f"Failed loading Piper TTS voice {model_path}: {exc}")
            return None


class LocalPiperTTS(tts.TTS):
    """Ultra-low-latency 100% offline neural Text-to-Speech via Piper ONNX."""

    def __init__(self, voice: str | None = None):
        self._voice = (voice or os.environ.get("PIPER_VOICE", "en_US-lessac-medium")).strip() or "en_US-lessac-medium"
        loaded = _get_piper_voice(self._voice)
        sr = int(getattr(getattr(loaded, "config", None), "sample_rate", 22050) or 22050)
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sr,
            num_channels=1,
        )

    @property
    def is_available(self) -> bool:
        return _resolve_piper_model_path(self._voice).exists()

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> tts.ChunkedStream:
        return PiperChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class PiperChunkedStream(tts.ChunkedStream):
    """Synthesize raw 16-bit PCM chunks from offline Piper ONNX voice to LiveKit AudioEmitter."""

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        clean = clean_spoken_text(self.input_text)
        if not clean:
            return

        voice = await asyncio.to_thread(_get_piper_voice, self._tts._voice)
        if voice is None:
            raise RuntimeError(f"Offline Piper TTS model not found for voice '{self._tts._voice}'")

        pcm_chunks = await asyncio.to_thread(
            lambda: [c.audio_int16_bytes for c in voice.synthesize(clean) if c.audio_int16_bytes]
        )
        if not pcm_chunks:
            return

        sr = int(getattr(getattr(voice, "config", None), "sample_rate", self._tts.sample_rate) or self._tts.sample_rate)
        output_emitter.initialize(
            request_id=uuid.uuid4().hex,
            sample_rate=sr,
            num_channels=1,
            mime_type="audio/pcm",
        )
        for pcm in pcm_chunks:
            output_emitter.push(pcm)
        output_emitter.flush()


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
            raise


def transcribe_audio_local(
    audio_bytes: bytes,
    model_size: Optional[str] = None,
    *,
    beam_size: Optional[int] = None,
    cpu_threads: Optional[int] = None,
    vad_filter: Optional[bool] = None,
    initial_prompt: Any = _UNSET,
) -> str:
    """Synchronous helper to transcribe audio bytes using local faster-whisper."""
    if not audio_bytes or len(audio_bytes) < 100:
        return ""
    try:
        return _transcribe_audio_bytes(
            audio_bytes,
            model_size,
            beam_size=beam_size,
            cpu_threads=cpu_threads,
            vad_filter=vad_filter,
            initial_prompt=initial_prompt,
        )
    except Exception as e:
        logger.error(f"transcribe_audio_local error: {e}")
        return ""


_LOCAL_TTS_CACHE: dict[tuple[str, str], bytes] = {}
_TTS_CACHE_LOCK = threading.Lock()


def _cache_get(cache_key: tuple[str, str]) -> bytes | None:
    with _TTS_CACHE_LOCK:
        return _LOCAL_TTS_CACHE.get(cache_key)


def _cache_put(cache_key: tuple[str, str], data: bytes) -> None:
    if not data:
        return
    with _TTS_CACHE_LOCK:
        if len(_LOCAL_TTS_CACHE) >= 128:
            _LOCAL_TTS_CACHE.pop(next(iter(_LOCAL_TTS_CACHE)))
        _LOCAL_TTS_CACHE[cache_key] = data


def synthesize_speech_piper_wav(text: str, voice_name: str | None = None) -> bytes:
    """Synthesize clean WAV bytes offline via Piper ONNX with thread-safe in-memory caching."""
    clean = clean_spoken_text(text)
    if not clean:
        return b""

    chosen = (voice_name or os.environ.get("PIPER_VOICE", "en_US-lessac-medium")).strip() or "en_US-lessac-medium"
    cache_key = (f"piper:{chosen}", clean)
    if len(clean) <= 180:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    voice = _get_piper_voice(chosen)
    if voice is None:
        return b""

    try:
        chunks = list(voice.synthesize(clean))
        if not chunks:
            return b""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(chunks[0].sample_channels)
            wf.setsampwidth(chunks[0].sample_width)
            wf.setframerate(chunks[0].sample_rate)
            for c in chunks:
                if c.audio_int16_bytes:
                    wf.writeframes(c.audio_int16_bytes)
        wav_bytes = buf.getvalue()
        if wav_bytes and len(clean) <= 180:
            _cache_put(cache_key, wav_bytes)
        return wav_bytes
    except Exception as exc:
        logger.warning(f"synthesize_speech_piper_wav error: {exc}")
        return b""


async def synthesize_speech_local_with_format_async(
    text: str,
    edge_voice: str = "en-US-ChristopherNeural",
    piper_voice: str | None = None,
) -> tuple[bytes, str]:
    """Synthesize speech using offline Piper WAV first, falling back to Edge-TTS unless STRICT_LOCAL_MODE is on."""
    clean = clean_spoken_text(text)
    if not clean:
        return b"", "wav"

    wav_bytes = await asyncio.to_thread(synthesize_speech_piper_wav, clean, piper_voice)
    if wav_bytes:
        return wav_bytes, "wav"

    if is_strict_local_mode():
        logger.warning("STRICT_LOCAL_MODE enabled and Piper TTS returned empty; skipping networked Edge-TTS fallback.")
        return b"", "wav"

    mp3_bytes = await synthesize_speech_local_async(clean, voice=edge_voice)
    return mp3_bytes, "mp3"


async def synthesize_speech_local_async(text: str, voice: str = "en-US-ChristopherNeural") -> bytes:
    """Async helper to synthesize speech using free neural edge-tts with thread-safe caching."""
    clean = clean_spoken_text(text)
    if not clean:
        return b""

    cache_key = (voice, clean)
    if len(clean) <= 180:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    try:
        import edge_tts

        communicate = edge_tts.Communicate(clean, voice)
        chunks = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks.append(chunk["data"])
        audio_bytes = b"".join(chunks)
        if audio_bytes and len(clean) <= 180:
            _cache_put(cache_key, audio_bytes)
        return audio_bytes
    except Exception as e:
        logger.error(f"synthesize_speech_local_async error: {e}")
        return b""


def synthesize_speech_local(text: str, voice: str = "en-US-ChristopherNeural") -> bytes:
    """Synchronous helper to synthesize speech using free neural edge-tts."""
    clean = clean_spoken_text(text)
    if not clean:
        return b""

    try:
        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(synthesize_speech_local_async(clean, voice))).result()
        except RuntimeError:
            return asyncio.run(synthesize_speech_local_async(clean, voice))
    except Exception as e:
        logger.error(f"synthesize_speech_local error: {e}")
        return b""
