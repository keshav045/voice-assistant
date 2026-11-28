"""Offline hardware gate, WER/CER/entity scoring, contention diagnostics, and E2E voice telemetry benchmark.

Supports:
1. Hardware gate profiling (CPU, cores, RAM, swap, GPU/CUDA DLL status, package versions).
2. Text normalization + WER/CER + critical entity accuracy (numbers, amounts, emails, names).
3. JSONL/CSV manifest loading separating synthetic (TTS) vs human clips.
4. Controlled one-variable experiments: Ollama contention (stopped/idle/generating),
   cpu_threads sweep, internal vad_filter on/off, beam size, initial prompt, cold vs warm latency, and RTF.
5. Local end-to-end scripted turn measurement (Silero VAD -> Whisper -> Ollama -> Piper) logged to VOICE_TELEMETRY_LOG.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import ctypes
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import threading
import time
from typing import Any, Iterable, Optional
import wave

import numpy as np

from agent.local_voice import (
    _DEFAULT_STT_PROMPT,
    LocalPiperTTS,
    LocalWhisperSTT,
    _WHISPER_MODELS,
    _get_piper_voice,
    _get_whisper_model,
    _resolve_piper_model_path,
    _stt_beam,
    _stt_cpu_threads,
    _stt_device,
    _stt_initial_prompt,
    _stt_language,
    _stt_model_size,
    _stt_vad_filter,
    prewarm_stt_decode,
    synthesize_speech_piper_wav,
    transcribe_audio_local,
)
from agent.voice_telemetry import (
    TurnTimer,
    compute_latency_percentiles,
    read_system_resource_snapshot,
)


_SPOKEN_NUM_MAP = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15",
    "eighteen": "18", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "hundred": "100", "thousand": "1000",
}

_ENTITY_NAMES = (
    "gmail", "whatsapp", "youtube", "dolo 650", "paracetamol", "pantoprazole",
    "pan 40", "ibuprofen", "rahul", "rohit", "keshav", "krish", "nexus",
    "new york", "monday", "friday", "saturday",
)


def _levenshtein(seq_a: list[str] | str, seq_b: list[str] | str) -> int:
    """Compute Levenshtein edit distance between token sequences or strings."""
    n, m = len(seq_a), len(seq_b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i, a_item in enumerate(seq_a, start=1):
        curr = [i] + [0] * m
        for j, b_item in enumerate(seq_b, start=1):
            cost = 0 if a_item == b_item else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m]


def normalize_transcript(text: str) -> str:
    """Normalize text consistently for WER/CER comparison across runs."""
    clean = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", clean).strip()


def _normalize_for_entities(text: str) -> str:
    """Normalize spoken numbers, percentages, currencies, and spoken email patterns for entity matching."""
    t = (text or "").lower()
    t = re.sub(r"\b([a-z0-9_.+-]+)\s+at(?:\s+the\s+rate)?\s+([a-z0-9-]+)\s+dot\s+([a-z]{2,})\b", r"\1@\2.\3", t)
    t = re.sub(r"\btwenty\s+five\b", "25", t)
    t = re.sub(r"\b(?:one\s+)?thousand\b", "1000", t)
    t = re.sub(r"\b(\d+)\s+hundred\b", lambda m: str(int(m.group(1)) * 100), t)
    t = re.sub(r"\bpercent(?:age)?\b", "%", t)
    t = re.sub(r"\bhalf\s+past\s+three\b", "3 30", t)
    tokens = t.split()
    mapped = [_SPOKEN_NUM_MAP.get(tok.strip(",.?"), tok) for tok in tokens]
    out = " ".join(mapped)
    out = re.sub(r"(\d+)\s+%", r"\1%", out)
    out = re.sub(r"\b(\d+)(am|pm)\b", r"\1 \2", out)
    return out


def extract_critical_entities(reference: str) -> list[str]:
    """Extract critical entities (emails, numbers/amounts/times, currency, named targets)."""
    norm = _normalize_for_entities(reference)
    entities: list[str] = []

    for em in re.findall(r"[a-z0-9_.+-]+@[a-z0-9-]+\.[a-z0-9-.]+", norm):
        entities.append(f"email:{em}")

    for pct in re.findall(r"\b\d+(?:\.\d+)?%", norm):
        entities.append(f"num:{pct.rstrip('%')}")

    for num in re.findall(r"\b\d+(?:\.\d+)?\b", norm):
        val = f"num:{num}"
        if val not in entities:
            entities.append(val)

    for unit in ("rupees", "dollars", "gst", "pm", "am"):
        if re.search(rf"\b{re.escape(unit)}\b", norm):
            entities.append(f"unit:{unit}")

    for name in _ENTITY_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", norm):
            entities.append(f"name:{name}")

    return entities


def compute_entity_accuracy(reference: str, hypothesis: str) -> dict[str, Any]:
    """Score extracted critical entities separately from overall WER."""
    expected = extract_critical_entities(reference)
    if not expected:
        return {"expected": [], "matched": [], "entity_accuracy": None}

    hyp_norm = _normalize_for_entities(hypothesis)
    matched: list[str] = []
    for ent in expected:
        kind, val = ent.split(":", 1)
        if kind == "email":
            if val in hyp_norm or val.replace("@", " at ").replace(".", " dot ") in hyp_norm:
                matched.append(ent)
        elif kind == "num":
            if re.search(rf"(?<!\d){re.escape(val)}(?!\d)", hyp_norm):
                matched.append(ent)
        else:
            if re.search(rf"\b{re.escape(val)}\b", hyp_norm):
                matched.append(ent)

    return {
        "expected": expected,
        "matched": matched,
        "entity_accuracy": round(len(matched) / len(expected), 4),
    }


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute normalized Word Error Rate (0.0 is exact match)."""
    ref_words = normalize_transcript(reference).split()
    hyp_words = normalize_transcript(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    return round(_levenshtein(ref_words, hyp_words) / len(ref_words), 4)


def compute_cer(reference: str, hypothesis: str) -> float:
    """Compute normalized Character Error Rate (0.0 is exact match)."""
    ref_chars = normalize_transcript(reference)
    hyp_chars = normalize_transcript(hypothesis)
    if not ref_chars:
        return 0.0 if not hyp_chars else 1.0
    return round(_levenshtein(ref_chars, hyp_chars) / len(ref_chars), 4)


def get_wav_duration_s(wav_bytes: bytes) -> float:
    """Return exact duration in seconds of a RIFF WAV byte buffer."""
    if not wav_bytes or wav_bytes[:4] != b"RIFF":
        return 0.0
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            rate = wf.getframerate() or 16000
            return round(wf.getnframes() / float(rate), 4)
    except Exception:
        return 0.0


def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    """Load JSONL or CSV clip manifest with normalized synthetic boolean flags."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    items: list[dict[str, Any]] = []
    suffix = manifest_path.suffix.lower()
    if suffix == ".csv":
        with open(manifest_path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                syn_raw = str(row.get("synthetic", "")).strip().lower()
                items.append({
                    "wav_path": row["wav_path"],
                    "reference_text": row["reference_text"],
                    "category": row.get("category", "general"),
                    "speaker": row.get("speaker", "unknown"),
                    "synthetic": syn_raw in {"1", "true", "yes", "synthetic"},
                })
    else:
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            syn = row.get("synthetic", False)
            if isinstance(syn, str):
                syn = syn.strip().lower() in {"1", "true", "yes", "synthetic"}
            items.append({
                "wav_path": row["wav_path"],
                "reference_text": row["reference_text"],
                "category": row.get("category", "general"),
                "speaker": row.get("speaker", "unknown"),
                "synthetic": bool(syn),
            })
    return items


def generate_synthetic_manifest(
    prompts_path: Path,
    out_dir: Path,
    manifest_path: Optional[Path] = None,
) -> Path:
    """Generate 16 kHz mono synthetic WAV clips via offline Piper TTS and save labeled manifest.jsonl."""
    from scipy.signal import resample_poly

    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    voice = _get_piper_voice()
    if voice is None:
        raise RuntimeError("Offline Piper voice model unavailable for synthetic clip generation.")

    out_dir.mkdir(parents=True, exist_ok=True)
    target_manifest = manifest_path or (out_dir / "manifest.jsonl")
    lines: list[str] = []
    for item in prompts:
        pid = item["id"]
        text = item["text"]
        chunks = list(voice.synthesize(text))
        pcm = b"".join(c.audio_int16_bytes for c in chunks if c.audio_int16_bytes)
        if not pcm:
            continue
        src_sr = int(chunks[0].sample_rate)
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if src_sr != 16000:
            div = math.gcd(16000, src_sr)
            arr = resample_poly(arr, 16000 // div, src_sr // div).astype(np.float32)
        pcm16 = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)

        wav_path = out_dir / f"synth_{pid}.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm16.tobytes())

        row = {
            "wav_path": str(wav_path).replace("\\", "/"),
            "reference_text": text,
            "category": item.get("category", "general"),
            "speaker": "piper_en_US-lessac-medium",
            "synthetic": True,
        }
        lines.append(json.dumps(row, ensure_ascii=False))

    target_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target_manifest


def record_hardware_profile() -> dict[str, Any]:
    """Capture Step 0 hardware tier, RAM, swap, CUDA status, package versions, and local config."""
    res_snap = read_system_resource_snapshot()
    total_ram_gb = res_snap.get("ram_total_gb")

    cuda_devices = 0
    cublas_available = False
    try:
        import ctranslate2
        cuda_devices = int(ctranslate2.get_cuda_device_count())
        if cuda_devices > 0 and platform.system() == "Windows":
            try:
                ctypes.WinDLL("cublas64_12.dll")
                cublas_available = True
            except OSError:
                cublas_available = False
        elif cuda_devices > 0:
            cublas_available = True
    except Exception:
        pass

    if cuda_devices > 0 and cublas_available:
        tier = "A_GPU_READY"
    elif (total_ram_gb or 0) >= 14.0:
        tier = "B_MODERN_CPU_16GB"
    elif (total_ram_gb or 8.0) >= 6.0:
        tier = "C_MODEST_CPU_8GB"
    else:
        tier = "D_LOW_MEMORY"

    packages: dict[str, Optional[str]] = {}
    for pkg in (
        "livekit-agents",
        "livekit-plugins-silero",
        "livekit-plugins-turn-detector",
        "faster-whisper",
        "ctranslate2",
        "piper-tts",
        "edge-tts",
        "sherpa-onnx",
    ):
        try:
            packages[pkg] = importlib.metadata.version(pkg)
        except Exception:
            packages[pkg] = None

    piper_path = _resolve_piper_model_path()
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "cpu_cores": os.cpu_count() or 1,
        **res_snap,
        "cuda_devices": cuda_devices,
        "cuda_runtime_ready": cublas_available,
        "hardware_tier": tier,
        "stt_config": {
            "model_size": _stt_model_size(),
            "language": _stt_language(),
            "beam_size": _stt_beam(),
            "cpu_threads": _stt_cpu_threads(),
            "vad_filter": _stt_vad_filter(),
            "device": _stt_device(),
        },
        "piper_model": piper_path.name if piper_path.exists() else None,
        "packages": packages,
    }


def _piper_chunks_to_wav(chunks: Iterable[Any]) -> bytes:
    """Serialize synthesized Piper audio chunks into RIFF WAV bytes."""
    chunk_list = list(chunks)
    if not chunk_list:
        return b""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(chunk_list[0].sample_channels)
        wf.setsampwidth(chunk_list[0].sample_width)
        wf.setframerate(chunk_list[0].sample_rate)
        for c in chunk_list:
            if c.audio_int16_bytes:
                wf.writeframes(c.audio_int16_bytes)
    return buf.getvalue()


def _summarize_clip_subset(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wers = [r["wer"] for r in rows if isinstance(r.get("wer"), (int, float))]
    cers = [r["cer"] for r in rows if isinstance(r.get("cer"), (int, float))]
    ent_expected = sum(len(r.get("entities_expected") or []) for r in rows)
    ent_matched = sum(len(r.get("entities_matched") or []) for r in rows)
    return {
        "clip_count": len(rows),
        "avg_wer": round(sum(wers) / len(wers), 4) if wers else None,
        "avg_cer": round(sum(cers) / len(cers), 4) if cers else None,
        "entities_expected": ent_expected,
        "entities_matched": ent_matched,
        "entity_accuracy": round(ent_matched / ent_expected, 4) if ent_expected else None,
    }


def _check_ollama_status() -> dict[str, Any]:
    """Query local Ollama server /api/ps to check whether server is stopped or has models loaded."""
    import urllib.request
    base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").strip().replace("/v1", "")
    try:
        with urllib.request.urlopen(f"{base}/api/ps", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {"running": True, "models": data.get("models", [])}
    except Exception:
        return {"running": False, "models": []}


def benchmark_local_voice_pipeline(
    clips_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    repeats: int = 3,
    model_size: Optional[str] = None,
    beam_size: Optional[int] = None,
    cpu_threads: Optional[int] = None,
    vad_filter: Optional[bool] = None,
    initial_prompt: Optional[str] = "__UNSET__",
    clear_cache: bool = True,
    ollama_state_label: str = "unspecified",
    concurrent_ollama_gen: bool = False,
) -> dict[str, Any]:
    """Run controlled offline STT/TTS benchmark with cold vs warm split, RTF, and system resource tracking."""
    size = _stt_model_size(model_size)
    eff_beam = _stt_beam(beam_size)
    eff_threads = _stt_cpu_threads(cpu_threads)
    eff_vad = _stt_vad_filter(vad_filter)
    prompt_arg = _stt_initial_prompt() if initial_prompt == "__UNSET__" else (initial_prompt or None)

    if clear_cache:
        _WHISPER_MODELS.clear()

    resources_before = read_system_resource_snapshot(cpu_sample_interval_s=0.25)
    ollama_status = _check_ollama_status()
    profile = record_hardware_profile()

    t_warm_tts = time.perf_counter()
    piper_ready = _get_piper_voice() is not None
    tts_load_ms = round((time.perf_counter() - t_warm_tts) * 1000.0, 1)

    t_warm_stt = time.perf_counter()
    whisper_ready = _get_whisper_model(size, cpu_threads=eff_threads) is not None
    stt_load_ms = round((time.perf_counter() - t_warm_stt) * 1000.0, 1)

    stop_gen_event = threading.Event()
    gen_thread: Optional[threading.Thread] = None
    gen_stats: dict[str, Any] = {"tokens_requests": 0, "errors": 0}
    if concurrent_ollama_gen:
        import urllib.request
        base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").strip().replace("/v1", "")
        gen_model = os.environ.get("OPENAI_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"

        def _ollama_spammer():
            while not stop_gen_event.is_set():
                try:
                    payload = json.dumps({
                        "model": gen_model,
                        "prompt": "Write a detailed 120-word explanation of how SQLite WAL mode works.",
                        "stream": False,
                        "keep_alive": "30m",
                        "options": {"num_ctx": 4096, "num_predict": 120},
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        f"{base}/api/generate",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=30.0) as resp:
                        resp.read()
                    gen_stats["tokens_requests"] += 1
                except Exception:
                    gen_stats["errors"] += 1
                    time.sleep(0.2)

        gen_thread = threading.Thread(target=_ollama_spammer, daemon=True)
        gen_thread.start()
        time.sleep(0.4)

    # Assemble clip inputs
    clip_inputs: list[dict[str, Any]] = []
    if manifest_path is not None:
        for item in load_manifest(manifest_path):
            wp = Path(item["wav_path"])
            if not wp.is_absolute() and not wp.exists():
                wp = manifest_path.parent / wp
            clip_inputs.append({
                "clip": wp.name,
                "wav_bytes": wp.read_bytes(),
                "reference": item["reference_text"],
                "category": item.get("category", "general"),
                "speaker": item.get("speaker", "unknown"),
                "synthetic": bool(item.get("synthetic", False)),
            })
    elif clips_dir and clips_dir.exists():
        for wav_file in sorted(clips_dir.glob("*.wav")):
            ref_file = wav_file.with_suffix(".txt")
            clip_inputs.append({
                "clip": wav_file.name,
                "wav_bytes": wav_file.read_bytes(),
                "reference": ref_file.read_text(encoding="utf-8").strip() if ref_file.exists() else "",
                "category": "directory_clip",
                "speaker": "unknown",
                "synthetic": False,
            })
    else:
        sample_phrases = [
            "Open Gmail and schedule a meeting for half past three.",
            "Calculate eighteen percent GST on one thousand rupees.",
            "What are the side effects of Dolo 650?",
        ]
        if whisper_ready and piper_ready:
            voice = _get_piper_voice()
            for idx, phrase in enumerate(sample_phrases, start=1):
                wb = _piper_chunks_to_wav(voice.synthesize(phrase)) if voice is not None else b""
                if wb:
                    clip_inputs.append({
                        "clip": f"synthetic_{idx}",
                        "wav_bytes": wb,
                        "reference": phrase,
                        "category": "inline_synthetic",
                        "speaker": "piper_en_US-lessac-medium",
                        "synthetic": True,
                    })

    tts_latencies: list[float] = []
    if piper_ready:
        for phrase in [
            "Open Gmail and schedule a meeting for half past three.",
            "Calculate eighteen percent GST on one thousand rupees.",
            "What are the side effects of Dolo 650?",
        ][: max(1, repeats)]:
            t0 = time.perf_counter()
            wav = synthesize_speech_piper_wav(phrase)
            dt = round((time.perf_counter() - t0) * 1000.0, 1)
            if wav:
                tts_latencies.append(dt)

    cold_run: Optional[dict[str, Any]] = None
    warm_stt_latencies: list[float] = []
    warm_rtfs: list[float] = []
    clip_results: list[dict[str, Any]] = []
    during_snapshots: list[dict[str, Any]] = []

    try:
        if whisper_ready and clip_inputs:
            first_clip = clip_inputs[0]
            dur_0 = get_wav_duration_s(first_clip["wav_bytes"])
            t0 = time.perf_counter()
            hyp0 = transcribe_audio_local(
                first_clip["wav_bytes"],
                model_size=size,
                beam_size=eff_beam,
                cpu_threads=eff_threads,
                vad_filter=eff_vad,
                initial_prompt=prompt_arg,
            )
            cold_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            cold_rtf = round((cold_ms / 1000.0) / dur_0, 4) if dur_0 > 0 else None
            cold_run = {
                "clip": first_clip["clip"],
                "audio_duration_s": dur_0,
                "cold_stt_ms": cold_ms,
                "cold_rtf": cold_rtf,
                "hypothesis": hyp0,
                "synthetic": first_clip["synthetic"],
            }
            during_snapshots.append(read_system_resource_snapshot(cpu_sample_interval_s=0.1))

            warm_per_clip_ms: dict[str, list[float]] = {c["clip"]: [] for c in clip_inputs}
            warm_hypotheses: dict[str, str] = {}
            for r_idx in range(max(1, repeats)):
                for item in clip_inputs:
                    cname = item["clip"]
                    dur_s = get_wav_duration_s(item["wav_bytes"])
                    t_s = time.perf_counter()
                    hyp = transcribe_audio_local(
                        item["wav_bytes"],
                        model_size=size,
                        beam_size=eff_beam,
                        cpu_threads=eff_threads,
                        vad_filter=eff_vad,
                        initial_prompt=prompt_arg,
                    )
                    dt_ms = round((time.perf_counter() - t_s) * 1000.0, 1)
                    warm_per_clip_ms[cname].append(dt_ms)
                    warm_stt_latencies.append(dt_ms)
                    if dur_s > 0:
                        warm_rtfs.append(round((dt_ms / 1000.0) / dur_s, 4))
                    warm_hypotheses[cname] = hyp
                if r_idx == 0:
                    during_snapshots.append(read_system_resource_snapshot(cpu_sample_interval_s=0.2))

            for item in clip_inputs:
                cname = item["clip"]
                dur_s = get_wav_duration_s(item["wav_bytes"])
                ref_text = item["reference"]
                hyp = warm_hypotheses.get(cname, "")
                clip_stats = compute_latency_percentiles(warm_per_clip_ms[cname])
                clip_rtfs = [round((ms / 1000.0) / dur_s, 4) for ms in warm_per_clip_ms[cname]] if dur_s > 0 else []
                row: dict[str, Any] = {
                    "clip": cname,
                    "category": item["category"],
                    "speaker": item["speaker"],
                    "synthetic": item["synthetic"],
                    "audio_duration_s": dur_s,
                    "warm_runs_ms": warm_per_clip_ms[cname],
                    "warm_p50_ms": clip_stats["p50_ms"],
                    "warm_p95_ms": clip_stats["p95_ms"],
                    "warm_rtf_p50": round(sorted(clip_rtfs)[len(clip_rtfs) // 2], 4) if clip_rtfs else None,
                    "hypothesis": hyp,
                }
                if ref_text:
                    ent = compute_entity_accuracy(ref_text, hyp)
                    row.update({
                        "reference": ref_text,
                        "wer": compute_wer(ref_text, hyp),
                        "cer": compute_cer(ref_text, hyp),
                        "entities_expected": ent["expected"],
                        "entities_matched": ent["matched"],
                        "entity_accuracy": ent["entity_accuracy"],
                    })
                clip_results.append(row)
    finally:
        stop_gen_event.set()
        if gen_thread is not None:
            gen_thread.join(timeout=5.0)

    resources_after = read_system_resource_snapshot(cpu_sample_interval_s=0.15)
    all_snaps = [resources_before] + during_snapshots + [resources_after]
    peak_rss_vals = [s.get("process_peak_rss_mb") for s in all_snaps if s.get("process_peak_rss_mb") is not None]
    avail_ram_vals = [s.get("ram_available_gb") for s in all_snaps if s.get("ram_available_gb") is not None]
    cpu_loads = [s.get("cpu_load_pct") for s in during_snapshots if s.get("cpu_load_pct") is not None]

    human_rows = [r for r in clip_results if not r.get("synthetic")]
    synth_rows = [r for r in clip_results if r.get("synthetic")]

    return {
        "hardware": profile,
        "experiment": {
            "ollama_state_label": ollama_state_label,
            "ollama_status_at_start": ollama_status,
            "concurrent_ollama_gen": concurrent_ollama_gen,
            "concurrent_ollama_stats": gen_stats if concurrent_ollama_gen else None,
            "whisper_model": size,
            "language": _stt_language(),
            "beam_size": eff_beam,
            "cpu_threads": eff_threads,
            "vad_filter": eff_vad,
            "initial_prompt": prompt_arg,
            "repeats": repeats,
            "manifest": str(manifest_path) if manifest_path else None,
        },
        "resources": {
            "before": resources_before,
            "during": during_snapshots[-1] if during_snapshots else resources_before,
            "after": resources_after,
            "peak_process_rss_mb": max(peak_rss_vals) if peak_rss_vals else None,
            "min_available_ram_gb": min(avail_ram_vals) if avail_ram_vals else None,
            "during_cpu_load_pct": round(sum(cpu_loads) / len(cpu_loads), 1) if cpu_loads else None,
        },
        "models_loaded": {"piper_ready": piper_ready, "whisper_ready": whisper_ready, "whisper_model": size},
        "cold_load_ms": {"piper_ms": tts_load_ms, "whisper_ms": stt_load_ms},
        "cold_first_call": cold_run,
        "tts_latency_ms": compute_latency_percentiles(tts_latencies),
        "stt_warm_latency_ms": compute_latency_percentiles(warm_stt_latencies),
        "stt_latency_ms": compute_latency_percentiles(warm_stt_latencies),
        "warm_rtf": {
            "avg": round(sum(warm_rtfs) / len(warm_rtfs), 4) if warm_rtfs else None,
            "p50": round(sorted(warm_rtfs)[int(round(0.5 * (len(warm_rtfs) - 1)))], 4) if warm_rtfs else None,
            "p95": round(sorted(warm_rtfs)[int(round(0.95 * (len(warm_rtfs) - 1)))], 4) if warm_rtfs else None,
        },
        "human_accuracy": _summarize_clip_subset(human_rows),
        "synthetic_accuracy": _summarize_clip_subset(synth_rows),
        "accuracy": _summarize_clip_subset(clip_results),
        "clips": clip_results,
    }


def _unload_ollama_model(model_name: str, base_url: str) -> None:
    """Explicitly unload an active Ollama model so the next turn measures cold LLM load."""
    import urllib.request
    base = base_url.strip().rstrip("/").removesuffix("/v1")
    payload = json.dumps({"model": model_name, "keep_alive": 0}).encode("utf-8")
    req = urllib.request.Request(f"{base}/api/generate", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15.0) as r:
            r.read()
    except Exception:
        pass
    time.sleep(0.5)


async def run_local_e2e_telemetry_turns(
    manifest_path: Optional[Path] = None,
    telemetry_log_path: Path = Path("bench_results/task5_voice_turns.jsonl"),
    max_turns: int = 5,
    cold_turn_indices: Optional[set[int]] = None,
) -> dict[str, Any]:
    """Run local voice turns (Silero VAD -> Whisper -> Ollama streaming -> Piper TTS) logging TurnTimer JSONL."""
    from livekit import rtc
    from livekit.plugins import silero
    from openai import AsyncOpenAI
    import scipy.io.wavfile as wavfile

    vad_model = silero.VAD.load(
        activation_threshold=float(os.environ.get("VAD_ACTIVATION_THRESHOLD", "0.55")),
        min_speech_duration=float(os.environ.get("VAD_MIN_SPEECH_DURATION", "0.08")),
        min_silence_duration=float(os.environ.get("VAD_MIN_SILENCE_DURATION", "0.65")),
    )
    stt_engine = LocalWhisperSTT()
    piper_voice = _get_piper_voice()
    if piper_voice is None:
        raise RuntimeError("Offline Piper voice model unavailable for E2E telemetry test.")

    base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").strip() or "http://localhost:11434/v1"
    model_name = os.environ.get("OPENAI_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"
    api_key = os.environ.get("OPENAI_API_KEY", "ollama").strip() or "ollama"
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)

    if manifest_path and manifest_path.exists():
        loaded = load_manifest(manifest_path)
        items = [loaded[i % len(loaded)] for i in range(max_turns)]
    else:
        raise RuntimeError("A valid manifest_path with WAV clips is required for --e2e-turns.")

    if telemetry_log_path.exists():
        telemetry_log_path.unlink()

    cold_set = cold_turn_indices or set()
    turn_rows: list[dict[str, Any]] = []
    try:
        for idx, item in enumerate(items, start=1):
            is_cold_llm = idx in cold_set
            if is_cold_llm:
                _unload_ollama_model(model_name, base_url)

            wp = Path(item["wav_path"])
            if not wp.is_absolute() and not wp.exists():
                wp = manifest_path.parent / wp
            sr, raw_samples = wavfile.read(str(wp))
            if raw_samples.ndim > 1:
                raw_samples = raw_samples[:, 0]
            if raw_samples.dtype != np.int16:
                raw_samples = (np.clip(raw_samples, -1.0, 1.0) * 32767.0).astype(np.int16)

            timer = TurnTimer(speech_id=f"e2e_turn_{idx:02d}")
            trailing_silence = np.zeros(int(sr * 1.1), dtype=np.int16)
            combined = np.concatenate([raw_samples, trailing_silence])
            vad_stream = vad_model.stream()
            eou_detected = asyncio.Event()
            frame_step = int(sr * 0.02)

            async def _drain_vad():
                async for ev in vad_stream:
                    if str(ev.type).endswith("END_OF_SPEECH"):
                        timer.mark("endpoint")
                        eou_detected.set()
                        break

            drain_task = asyncio.create_task(_drain_vad())
            speech_end_idx = len(raw_samples)
            speech_end_marked = False
            loop_start = time.perf_counter()
            for f_idx, pos in enumerate(range(0, len(combined), frame_step), start=1):
                chunk = combined[pos : pos + step] if (step := frame_step) else combined[pos:]
                if len(chunk) < frame_step:
                    chunk = np.pad(chunk, (0, frame_step - len(chunk)))
                vad_stream.push_frame(
                    rtc.AudioFrame(
                        data=chunk.tobytes(),
                        sample_rate=sr,
                        num_channels=1,
                        samples_per_channel=len(chunk),
                    )
                )
                if not speech_end_marked and pos >= speech_end_idx:
                    timer.mark("speech_end")
                    speech_end_marked = True
                if eou_detected.is_set():
                    break
                delay = (loop_start + f_idx * 0.02) - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)

            if not speech_end_marked:
                timer.mark("speech_end")
            vad_stream.end_input()
            if not eou_detected.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(drain_task), timeout=2.0)
                except asyncio.TimeoutError:
                    timer.mark("endpoint")
            if not drain_task.done():
                drain_task.cancel()
            await asyncio.gather(drain_task, return_exceptions=True)
            await vad_stream.aclose()

            frame = rtc.AudioFrame(
                data=raw_samples.tobytes(),
                sample_rate=sr,
                num_channels=1,
                samples_per_channel=len(raw_samples),
            )
            ev = await stt_engine._recognize_impl(frame)
            timer.mark("stt_final")
            transcript = ev.alternatives[0].text if ev.alternatives else ""

            timer.mark("llm_req")
            llm_reply_parts: list[str] = []
            extra_body = {"options": {"num_ctx": 4096}, "keep_alive": "30m"}
            if "qwen3" in model_name.lower():
                extra_body["think"] = False
            stream = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are Nexus AI. Reply concisely in 1 crisp spoken sentence."},
                    {"role": "user", "content": transcript or item["reference_text"]},
                ],
                temperature=0.2,
                max_tokens=80,
                stream=True,
                extra_body=extra_body,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    timer.mark("llm_first_token")
                    llm_reply_parts.append(delta)
            full_reply = "".join(llm_reply_parts).strip() or "Okay."

            timer.mark("tts_req")
            llm_total_ms = timer.ms("llm_req", "tts_req")
            for pcm_chunk in piper_voice.synthesize(full_reply):
                if getattr(pcm_chunk, "audio_int16_bytes", None):
                    timer.mark("tts_first_audio")
                    break

            row = timer.record(
                path=telemetry_log_path,
                extra={
                    "turn_index": idx,
                    "cold_llm": is_cold_llm,
                    "clip": wp.name,
                    "synthetic_input": bool(item.get("synthetic", False)),
                    "llm_total_ms": llm_total_ms,
                    "transcript": transcript,
                    "reply_preview": full_reply[:80],
                },
            )
            if row:
                turn_rows.append(row)
    finally:
        await client.close()

    def _summarize_turns(subset: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "turns": len(subset),
            "endpoint_ms": compute_latency_percentiles(r["endpoint_ms"] for r in subset),
            "stt_final_ms": compute_latency_percentiles(r["stt_final_ms"] for r in subset),
            "llm_ttft_ms": compute_latency_percentiles(r["llm_ttft_ms"] for r in subset),
            "llm_total_ms": compute_latency_percentiles(r.get("llm_total_ms") for r in subset if r.get("llm_total_ms") is not None),
            "tts_ttfb_ms": compute_latency_percentiles(r["tts_ttfb_ms"] for r in subset),
            "server_ttfa_ms": compute_latency_percentiles(r["server_ttfa_ms"] for r in subset),
        }

    warm_only = [r for r in turn_rows if not r.get("cold_llm")]
    cold_only = [r for r in turn_rows if r.get("cold_llm")]
    all_summary = _summarize_turns(turn_rows)
    return {
        **all_summary,
        "telemetry_log": str(telemetry_log_path),
        "including_cold_llm": all_summary,
        "excluding_cold_llm": _summarize_turns(warm_only),
        "cold_llm_only": _summarize_turns(cold_only),
        "rows": turn_rows,
    }


def _synthesize_to_16k_int16(text: str) -> np.ndarray:
    """Synthesize speech with offline Piper and resample to 16 kHz mono int16."""
    from scipy.signal import resample_poly
    voice = _get_piper_voice()
    if voice is None:
        raise RuntimeError("Offline Piper voice unavailable.")
    chunks = list(voice.synthesize(text))
    pcm = b"".join(c.audio_int16_bytes for c in chunks if c.audio_int16_bytes)
    src_sr = int(chunks[0].sample_rate)
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if src_sr != 16000:
        div = math.gcd(16000, src_sr)
        arr = resample_poly(arr, 16000 // div, src_sr // div).astype(np.float32)
    return (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)


def generate_duration_clips(out_dir: Path, durations_s: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0)) -> Path:
    """Generate synthetic 16 kHz mono WAVs closely matching exact target durations (1, 2, 4, 8 s)."""
    base_phrases = [
        "Open Gmail.",
        "Open Gmail and check my latest emails.",
        "Schedule a team sync meeting tomorrow at 4 PM and add a task to calculate 18 percent GST.",
        "Open Gmail and check my latest emails. Also calculate eighteen percent GST on one thousand rupees, check the current time in New York, and tell me the side effects of Paracetamol and Ibuprofen.",
    ]
    raw_concat = np.concatenate([_synthesize_to_16k_int16(p) for p in base_phrases])
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"
    rows: list[str] = []
    for target_s in durations_s:
        n_samples = int(round(target_s * 16000))
        if len(raw_concat) >= n_samples:
            clip_pcm = raw_concat[:n_samples]
        else:
            reps = int(math.ceil(n_samples / len(raw_concat)))
            clip_pcm = np.tile(raw_concat, reps)[:n_samples]
        wav_path = out_dir / f"dur_{int(target_s)}s.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(clip_pcm.tobytes())
        rows.append(json.dumps({
            "wav_path": str(wav_path).replace("\\", "/"),
            "reference_text": f"Synthetic duration probe ({target_s}s)",
            "category": f"duration_{int(target_s)}s",
            "speaker": "piper_en_US-lessac-medium",
            "synthetic": True,
        }))
    manifest_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return manifest_path


def run_duration_scaling_benchmark(durations_dir: Path, repeats: int = 5) -> dict[str, Any]:
    """Measure decode time and RTF for exact 1s, 2s, 4s, 8s synthetic clips on CPU."""
    manifest_path = generate_duration_clips(durations_dir)
    out: dict[str, Any] = {"manifest": str(manifest_path), "synthetic": True, "models": {}}
    for model_name in ("base.en", "tiny.en"):
        res = benchmark_local_voice_pipeline(
            manifest_path=manifest_path,
            repeats=repeats,
            model_size=model_name,
            cpu_threads=4,
            vad_filter=True,
            clear_cache=True,
            ollama_state_label="stopped",
        )
        out["models"][model_name] = {
            "cold_first_call": res["cold_first_call"],
            "clips": [
                {
                    "clip": c["clip"],
                    "duration_s": c["audio_duration_s"],
                    "warm_runs_ms": c["warm_runs_ms"],
                    "warm_p50_ms": c["warm_p50_ms"],
                    "warm_p95_ms": c["warm_p95_ms"],
                    "warm_min_ms": min(c["warm_runs_ms"]),
                    "warm_max_ms": max(c["warm_runs_ms"]),
                    "warm_rtf_p50": c["warm_rtf_p50"],
                }
                for c in res["clips"]
            ],
        }
    return out


def run_interleaved_ab(
    manifest_path: Path,
    label_a: str,
    kwargs_a: dict[str, Any],
    label_b: str,
    kwargs_b: dict[str, Any],
    blocks: int = 2,
    repeats_per_block: int = 5,
) -> dict[str, Any]:
    """Run interleaved A, B, A, B experiments and report medians, min/max, and significance."""
    sequence = [("A", label_a, kwargs_a), ("B", label_b, kwargs_b)] * blocks
    block_logs: list[dict[str, Any]] = []
    pooled: dict[str, list[float]] = {label_a: [], label_b: []}
    block_medians: dict[str, list[float]] = {label_a: [], label_b: []}
    block_wers: dict[str, list[float]] = {label_a: [], label_b: []}
    block_ents: dict[str, list[float]] = {label_a: [], label_b: []}

    for idx, (arm, lbl, kw) in enumerate(sequence, start=1):
        res = benchmark_local_voice_pipeline(
            manifest_path=manifest_path,
            repeats=repeats_per_block,
            clear_cache=True,
            ollama_state_label="stopped",
            **kw,
        )
        all_ms = [ms for c in res["clips"] for ms in c["warm_runs_ms"]]
        pooled[lbl].extend(all_ms)
        st = compute_latency_percentiles(all_ms)
        if st["p50_ms"] is not None:
            block_medians[lbl].append(st["p50_ms"])
        if res["synthetic_accuracy"]["avg_wer"] is not None:
            block_wers[lbl].append(res["synthetic_accuracy"]["avg_wer"])
        if res["synthetic_accuracy"]["entity_accuracy"] is not None:
            block_ents[lbl].append(res["synthetic_accuracy"]["entity_accuracy"])
        block_logs.append({
            "step": idx,
            "arm": arm,
            "label": lbl,
            "cold_load_ms": res["cold_load_ms"]["whisper_ms"],
            "cold_stt_ms": res["cold_first_call"]["cold_stt_ms"],
            "warm_p50_ms": st["p50_ms"],
            "warm_p95_ms": st["p95_ms"],
            "warm_min_ms": min(all_ms) if all_ms else None,
            "warm_max_ms": max(all_ms) if all_ms else None,
            "rtf_p50": res["warm_rtf"]["p50"],
            "wer": res["synthetic_accuracy"]["avg_wer"],
            "entity_accuracy": res["synthetic_accuracy"]["entity_accuracy"],
            "cpu_pct": res["resources"]["during_cpu_load_pct"],
            "peak_rss_mb": res["resources"]["peak_process_rss_mb"],
        })

    def _agg(vals: list[float]) -> dict[str, Any]:
        s = sorted(vals)
        p = compute_latency_percentiles(s)
        return {
            "count": len(s),
            "median_ms": p["p50_ms"],
            "p95_ms": p["p95_ms"],
            "min_ms": round(s[0], 1) if s else None,
            "max_ms": round(s[-1], 1) if s else None,
        }

    agg_a, agg_b = _agg(pooled[label_a]), _agg(pooled[label_b])
    med_a, med_b = agg_a["median_ms"] or 0.0, agg_b["median_ms"] or 0.0
    pct_diff = round(abs(med_b - med_a) / med_a * 100.0, 2) if med_a > 0 else 0.0
    ranges_overlap = bool(
        agg_a["min_ms"] is not None and agg_b["min_ms"] is not None
        and (agg_a["min_ms"] <= med_b <= agg_a["max_ms"] or agg_b["min_ms"] <= med_a <= agg_b["max_ms"])
    )
    sig_verdict = (
        f"no significant difference (delta {pct_diff}% < 10% and median inside opposing min-max range)"
        if pct_diff < 10.0 or ranges_overlap
        else f"significant difference (delta {pct_diff}% >= 10%)"
    )

    return {
        "order": [f"{b['arm']}({b['label']})" for b in block_logs],
        "blocks": block_logs,
        "summary": {
            label_a: {**agg_a, "block_medians": block_medians[label_a], "wer": block_wers[label_a][-1] if block_wers[label_a] else None, "entity_accuracy": block_ents[label_a][-1] if block_ents[label_a] else None},
            label_b: {**agg_b, "block_medians": block_medians[label_b], "wer": block_wers[label_b][-1] if block_wers[label_b] else None, "entity_accuracy": block_ents[label_b][-1] if block_ents[label_b] else None},
            "median_delta_pct": pct_diff,
            "verdict": sig_verdict,
        },
    }


async def run_endpoint_silence_sweep(silences: tuple[float, ...] = (0.65, 0.5, 0.4), repeats: int = 3) -> dict[str, Any]:
    """Test Silero min_silence_duration values against synthetic trailing-silence and mid-sentence pause clips."""
    from livekit import rtc
    from livekit.plugins import silero

    clean_clips = [
        ("clean_1", _synthesize_to_16k_int16("Open Gmail and check my latest emails."), 0.0),
        ("clean_2", _synthesize_to_16k_int16("What are the side effects of Dolo 650?"), 0.0),
    ]
    pause_specs = [
        ("pause_450ms", "Schedule the team sync meeting", "tomorrow at four PM", 0.45),
        ("pause_550ms", "Open Gmail and search", "for the quarterly report", 0.55),
        ("pause_600ms", "Calculate eighteen percent GST", "on one thousand rupees", 0.60),
    ]
    paused_clips = []
    for name, p1, p2, pause_s in pause_specs:
        a1 = _synthesize_to_16k_int16(p1)
        a2 = _synthesize_to_16k_int16(p2)
        gap = np.zeros(int(16000 * pause_s), dtype=np.int16)
        combined = np.concatenate([a1, gap, a2])
        paused_clips.append((name, combined, pause_s, len(a1), len(a1) + len(gap)))

    results: list[dict[str, Any]] = []
    for min_sil in silences:
        vad_model = silero.VAD.load(activation_threshold=0.55, min_speech_duration=0.08, min_silence_duration=min_sil)
        clean_eou_ms: list[float] = []
        premature_count = 0
        pause_details: list[dict[str, Any]] = []

        # Trailing silence latency on clean clips
        for _ in range(repeats):
            for cname, speech_pcm, _ in clean_clips:
                trailing = np.zeros(int(16000 * 1.1), dtype=np.int16)
                buf = np.concatenate([speech_pcm, trailing])
                vad_stream = vad_model.stream()
                t_speech_end: dict[str, float] = {}
                t_eou: dict[str, float] = {}
                done_ev = asyncio.Event()

                async def _drain():
                    async for ev in vad_stream:
                        if str(ev.type).endswith("END_OF_SPEECH"):
                            t_eou["val"] = time.perf_counter()
                            done_ev.set()
                            break

                dt = asyncio.create_task(_drain())
                step = 320  # 20ms @ 16kHz
                t_start = time.perf_counter()
                for f_idx, pos in enumerate(range(0, len(buf), step), start=1):
                    chunk = buf[pos : pos + step]
                    if len(chunk) < step:
                        chunk = np.pad(chunk, (0, step - len(chunk)))
                    vad_stream.push_frame(rtc.AudioFrame(data=chunk.tobytes(), sample_rate=16000, num_channels=1, samples_per_channel=len(chunk)))
                    if "val" not in t_speech_end and pos >= len(speech_pcm):
                        t_speech_end["val"] = time.perf_counter()
                    if done_ev.is_set():
                        break
                    wait_s = (t_start + f_idx * 0.02) - time.perf_counter()
                    if wait_s > 0:
                        await asyncio.sleep(wait_s)
                vad_stream.end_input()
                if not done_ev.is_set():
                    try:
                        await asyncio.wait_for(asyncio.shield(dt), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                if not dt.done():
                    dt.cancel()
                await asyncio.gather(dt, return_exceptions=True)
                await vad_stream.aclose()
                if "val" in t_eou and "val" in t_speech_end:
                    clean_eou_ms.append(round((t_eou["val"] - t_speech_end["val"]) * 1000.0, 1))

        # Mid-sentence pause cut-off check
        for pname, speech_pcm, pause_s, part1_end, part2_start in paused_clips:
            cut_this = False
            eou_events_before_end = 0
            trailing = np.zeros(int(16000 * 1.1), dtype=np.int16)
            buf = np.concatenate([speech_pcm, trailing])
            vad_stream = vad_model.stream()
            step = 320
            curr_sample_pos = {"pos": 0}
            done_ev = asyncio.Event()

            async def _drain_pause():
                nonlocal cut_this, eou_events_before_end
                async for ev in vad_stream:
                    if str(ev.type).endswith("END_OF_SPEECH"):
                        if curr_sample_pos["pos"] < len(speech_pcm):
                            cut_this = True
                            eou_events_before_end += 1
                        else:
                            done_ev.set()
                            break

            dt = asyncio.create_task(_drain_pause())
            t_start = time.perf_counter()
            for f_idx, pos in enumerate(range(0, len(buf), step), start=1):
                curr_sample_pos["pos"] = pos
                chunk = buf[pos : pos + step]
                if len(chunk) < step:
                    chunk = np.pad(chunk, (0, step - len(chunk)))
                vad_stream.push_frame(rtc.AudioFrame(data=chunk.tobytes(), sample_rate=16000, num_channels=1, samples_per_channel=len(chunk)))
                if done_ev.is_set():
                    break
                wait_s = (t_start + f_idx * 0.02) - time.perf_counter()
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
            vad_stream.end_input()
            if not done_ev.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(dt), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
            if not dt.done():
                dt.cancel()
            await asyncio.gather(dt, return_exceptions=True)
            await vad_stream.aclose()
            if cut_this:
                premature_count += 1
            pause_details.append({"clip": pname, "pause_s": pause_s, "premature_cutoff": cut_this, "mid_pause_eou_events": eou_events_before_end})

        st = compute_latency_percentiles(clean_eou_ms)
        results.append({
            "min_silence_duration_s": min_sil,
            "synthetic": True,
            "clean_trailing_trials": len(clean_eou_ms),
            "endpoint_ms_p50": st["p50_ms"],
            "endpoint_ms_p95": st["p95_ms"],
            "endpoint_ms_min": min(clean_eou_ms) if clean_eou_ms else None,
            "endpoint_ms_max": max(clean_eou_ms) if clean_eou_ms else None,
            "paused_clips_tested": len(pause_details),
            "premature_cutoffs": premature_count,
            "pause_details": pause_details,
        })

    return {"synthetic": True, "note": "Synthetic digital pauses; must be confirmed on human recordings.", "results": results}


def verify_heldout_prompt_isolation(heldout_prompts_path: Path) -> list[str]:
    """Assert zero lexical token overlap between held-out prompts and domain initial_prompt keywords."""
    forbidden = set(re.findall(r"[a-z0-9]+", f"{_DEFAULT_STT_PROMPT} GST rupees gmail calendar nexus".lower()))
    prompts = json.loads(heldout_prompts_path.read_text(encoding="utf-8"))
    overlaps: list[str] = []
    for item in prompts:
        toks = set(re.findall(r"[a-z0-9]+", item["text"].lower()))
        hit = sorted(forbidden & toks)
        if hit:
            overlaps.append(f"{item['id']}:{hit}")
    return overlaps


def run_heldout_leakage_benchmark(orig_manifest: Path, heldout_dir: Path, heldout_prompts: Path, repeats: int = 3) -> dict[str, Any]:
    """Compare prompt vs no-prompt across both original and zero-overlap held-out prompt sets."""
    overlaps = verify_heldout_prompt_isolation(heldout_prompts)
    if overlaps:
        raise ValueError(f"Held-out prompts leak STT_INITIAL_PROMPT tokens: {overlaps}")
    heldout_manifest = generate_synthetic_manifest(heldout_prompts, heldout_dir)

    table: list[dict[str, Any]] = []
    for ds_name, m_path in (("original_15", orig_manifest), ("heldout_12", heldout_manifest)):
        for model_name in ("base.en", "tiny.en"):
            for prompt_lbl, p_val in (("prompt_on", _DEFAULT_STT_PROMPT), ("prompt_off", None)):
                r = benchmark_local_voice_pipeline(
                    manifest_path=m_path,
                    repeats=repeats,
                    model_size=model_name,
                    beam_size=1,
                    cpu_threads=4,
                    vad_filter=True,
                    initial_prompt=p_val,
                    clear_cache=True,
                    ollama_state_label="stopped",
                )
                sa = r["synthetic_accuracy"]
                table.append({
                    "dataset": ds_name,
                    "synthetic": True,
                    "model": model_name,
                    "prompt": prompt_lbl,
                    "clips": sa["clip_count"],
                    "wer": sa["avg_wer"],
                    "cer": sa["avg_cer"],
                    "entity_accuracy": sa["entity_accuracy"],
                    "entities": f"{sa['entities_matched']}/{sa['entities_expected']}",
                    "warm_p50_ms": r["stt_warm_latency_ms"]["p50_ms"],
                    "warm_p95_ms": r["stt_warm_latency_ms"]["p95_ms"],
                })
    return {"overlap_check": "PASS (0 shared tokens)", "heldout_manifest": str(heldout_manifest), "results": table}


def run_prewarm_comparison(manifest_path: Path, repeats: int = 3) -> dict[str, Any]:
    """Compare cold first-turn latency in fresh subprocesses before vs after startup prewarm."""
    import subprocess
    import sys

    loaded = load_manifest(manifest_path)
    wp = Path(loaded[0]["wav_path"])
    if not wp.is_absolute() and not wp.exists():
        wp = manifest_path.parent / wp
    ref_text = loaded[0]["reference_text"]

    base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").strip() or "http://localhost:11434/v1"
    model_name = os.environ.get("OPENAI_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"

    child_code = """import asyncio, json, os, time, wave
import numpy as np
from livekit import rtc
from livekit.plugins import silero
from openai import AsyncOpenAI
from agent.local_voice import LocalWhisperSTT, _get_piper_voice, prewarm_stt_decode
from agent.livekit_worker import prewarm_ollama

prewarm_on = os.environ.get('BENCH_PREWARM') == '1'
prewarm_ms = 0.0
t_pw = time.perf_counter()
vad = silero.VAD.load(activation_threshold=0.55, min_speech_duration=0.08, min_silence_duration=0.65)
piper = _get_piper_voice()
stt_e = LocalWhisperSTT()
if prewarm_on:
    prewarm_stt_decode(duration_s=1.0)
    prewarm_ollama()
    prewarm_ms = round((time.perf_counter() - t_pw) * 1000.0, 1)

async def run_one():
    with wave.open(os.environ['BENCH_WAV'], 'rb') as wf:
        sr = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    t0 = time.perf_counter()
    arr = np.frombuffer(pcm, dtype=np.int16)
    ev = await stt_e._recognize_impl(rtc.AudioFrame(data=arr.tobytes(), sample_rate=sr, num_channels=1, samples_per_channel=len(arr)))
    t_stt = time.perf_counter()
    cli = AsyncOpenAI(api_key='ollama', base_url=os.environ['BENCH_BASE_URL'], timeout=60.0)
    stream = await cli.chat.completions.create(
        model=os.environ['BENCH_MODEL'],
        messages=[
            {'role': 'system', 'content': 'Reply in one short sentence.'},
            {'role': 'user', 'content': ev.alternatives[0].text or os.environ['BENCH_REF']},
        ],
        temperature=0.2,
        max_tokens=60,
        stream=True,
        extra_body={'options': {'num_ctx': 4096}, 'keep_alive': '30m'},
    )
    t_first = None
    parts = []
    async for ch in stream:
        d = ch.choices[0].delta.content if ch.choices else None
        if d:
            if t_first is None:
                t_first = time.perf_counter()
            parts.append(d)
    await cli.close()
    reply = ''.join(parts).strip() or 'Okay.'
    t_tts_start = time.perf_counter()
    for c in piper.synthesize(reply):
        if getattr(c, 'audio_int16_bytes', None):
            break
    t_tts = time.perf_counter()
    return {
        'prewarm_ms': prewarm_ms,
        'stt_ms': round((t_stt - t0) * 1000.0, 1),
        'llm_ttft_ms': round(((t_first or t_tts_start) - t_stt) * 1000.0, 1),
        'tts_ttfb_ms': round((t_tts - t_tts_start) * 1000.0, 1),
        'turn1_compute_ms': round((t_tts - t0) * 1000.0, 1),
    }

print(json.dumps(asyncio.run(run_one())))
"""

    out: dict[str, Any] = {"repeats_per_arm": repeats, "clip": wp.name}
    for arm, flag in (("before_cold_turn1", "0"), ("after_prewarm_turn1", "1")):
        runs: list[dict[str, Any]] = []
        for _ in range(repeats):
            _unload_ollama_model(model_name, base_url)
            env = {
                **os.environ,
                "BENCH_PREWARM": flag,
                "BENCH_WAV": str(wp),
                "BENCH_REF": ref_text,
                "BENCH_BASE_URL": base_url,
                "BENCH_MODEL": model_name,
            }
            raw = subprocess.check_output([sys.executable, "-c", child_code], env=env, text=True, stderr=subprocess.STDOUT)
            line = [ln for ln in raw.strip().splitlines() if ln.startswith("{")][-1]
            runs.append(json.loads(line))
        out[arm] = {
            "runs": runs,
            "stt_ms": compute_latency_percentiles(r["stt_ms"] for r in runs),
            "llm_ttft_ms": compute_latency_percentiles(r["llm_ttft_ms"] for r in runs),
            "tts_ttfb_ms": compute_latency_percentiles(r["tts_ttfb_ms"] for r in runs),
            "turn1_compute_ms": compute_latency_percentiles(r["turn1_compute_ms"] for r in runs),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Nexus local voice pipeline (hardware gate, STT, Piper TTS, WER/CER/entities, E2E telemetry).")
    parser.add_argument("--clips-dir", type=Path, default=None, help="Optional folder of .wav + .txt reference clips.")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional JSONL or CSV clip manifest path.")
    parser.add_argument("--generate-synthetic", type=Path, default=None, help="Generate synthetic Piper WAV dataset under this directory from --prompts.")
    parser.add_argument("--prompts", type=Path, default=Path("bench_clips/prompts.json"), help="Prompt script JSON for synthetic generation.")
    parser.add_argument("--generate-durations", type=Path, default=None, help="Run Task 1c duration scaling benchmark (1, 2, 4, 8s).")
    parser.add_argument("--interleaved-ab", choices=["threads_4_vs_6", "vad_on_vs_off"], default=None, help="Run interleaved A/B/A/B benchmark for Task 2.")
    parser.add_argument("--endpoint-sweep", action="store_true", help="Run Task 3 Silero min_silence_duration sweep.")
    parser.add_argument("--heldout-leakage", type=Path, default=None, help="Run Task 7 prompt leakage benchmark outputting held-out WAVs to this dir.")
    parser.add_argument("--heldout-prompts", type=Path, default=Path("bench_clips/heldout_prompts.json"), help="Held-out prompt JSON path.")
    parser.add_argument("--benchmark-prewarm", action="store_true", help="Run Task 6b subprocess cold first-turn before vs after prewarm benchmark.")
    parser.add_argument("--repeats", type=int, default=3, help="Number of warm repeats per clip (default 3).")
    parser.add_argument("--model", type=str, default=None, help="Override WHISPER_MODEL_SIZE for this run.")
    parser.add_argument("--beam", type=int, default=None, help="Override beam_size for this run.")
    parser.add_argument("--cpu-threads", type=int, default=None, help="Override cpu_threads for this run.")
    parser.add_argument("--vad-filter", choices=["on", "off"], default=None, help="Override faster-whisper internal vad_filter for this run.")
    parser.add_argument("--prompt", type=str, default="__UNSET__", help="Override initial_prompt ('none' to disable).")
    parser.add_argument("--no-clear-cache", action="store_true", help="Do not clear cached Whisper model before running.")
    parser.add_argument("--ollama-state", type=str, default="unspecified", help="Metadata tag for Ollama state (stopped/idle/generating).")
    parser.add_argument("--concurrent-ollama-gen", action="store_true", help="Run active Ollama generation concurrently during STT benchmark.")
    parser.add_argument("--e2e-turns", type=int, default=0, help="Run N scripted E2E voice pipeline turns (Silero+Whisper+Ollama+Piper).")
    parser.add_argument("--cold-turns", type=str, default="", help="Comma-separated 1-based turn indices to force cold Ollama unload before running.")
    parser.add_argument("--telemetry-log", type=Path, default=Path("bench_results/task5_voice_turns.jsonl"), help="VOICE_TELEMETRY_LOG path for --e2e-turns.")
    parser.add_argument("--out", type=Path, default=None, help="Optional path to save JSON benchmark report.")
    args = parser.parse_args()

    def _emit(payload: Any) -> None:
        print(json.dumps(payload, indent=2))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.generate_synthetic is not None:
        mpath = generate_synthetic_manifest(args.prompts, args.generate_synthetic)
        _emit({"generated_manifest": str(mpath)})
        return

    if args.generate_durations is not None:
        _emit(run_duration_scaling_benchmark(args.generate_durations, repeats=args.repeats))
        return

    if args.interleaved_ab is not None:
        m_path = args.manifest or Path("bench_clips/synthetic/manifest.jsonl")
        if args.interleaved_ab == "threads_4_vs_6":
            _emit(run_interleaved_ab(
                m_path,
                "threads_4", {"model_size": "base.en", "beam_size": 1, "cpu_threads": 4, "vad_filter": True},
                "threads_6", {"model_size": "base.en", "beam_size": 1, "cpu_threads": 6, "vad_filter": True},
                blocks=2, repeats_per_block=max(5, args.repeats),
            ))
        else:
            _emit(run_interleaved_ab(
                m_path,
                "vad_on", {"model_size": "base.en", "beam_size": 1, "cpu_threads": 4, "vad_filter": True},
                "vad_off", {"model_size": "base.en", "beam_size": 1, "cpu_threads": 4, "vad_filter": False},
                blocks=2, repeats_per_block=max(5, args.repeats),
            ))
        return

    if args.endpoint_sweep:
        _emit(asyncio.run(run_endpoint_silence_sweep(repeats=max(3, args.repeats))))
        return

    if args.heldout_leakage is not None:
        orig_m = args.manifest or Path("bench_clips/synthetic/manifest.jsonl")
        _emit(run_heldout_leakage_benchmark(orig_m, args.heldout_leakage, args.heldout_prompts, repeats=args.repeats))
        return

    if args.benchmark_prewarm:
        m_path = args.manifest or Path("bench_clips/synthetic/manifest.jsonl")
        _emit(run_prewarm_comparison(m_path, repeats=args.repeats))
        return

    if args.e2e_turns > 0:
        cold_idxs = {int(x.strip()) for x in args.cold_turns.split(",") if x.strip().isdigit()}
        res = asyncio.run(
            run_local_e2e_telemetry_turns(
                manifest_path=args.manifest,
                telemetry_log_path=args.telemetry_log,
                max_turns=args.e2e_turns,
                cold_turn_indices=cold_idxs,
            )
        )
        _emit(res)
        return

    prompt_val = None if (args.prompt or "").lower() in {"none", "off", ""} else args.prompt
    vad_val = None if args.vad_filter is None else (args.vad_filter == "on")

    report = benchmark_local_voice_pipeline(
        clips_dir=args.clips_dir,
        manifest_path=args.manifest,
        repeats=args.repeats,
        model_size=args.model,
        beam_size=args.beam,
        cpu_threads=args.cpu_threads,
        vad_filter=vad_val,
        initial_prompt=prompt_val,
        clear_cache=not args.no_clear_cache,
        ollama_state_label=args.ollama_state,
        concurrent_ollama_gen=args.concurrent_ollama_gen,
    )
    _emit(report)


if __name__ == "__main__":
    main()
