"""Interactive CLI helper to record 16 kHz mono WAV voice clips and manifest rows.

Prints one prompt at a time from a script file (JSON), records audio from the
default microphone (either fixed duration or Enter-to-stop), writes a 16 kHz mono
16-bit PCM WAV file, and appends a manifest row (wav_path, reference_text, category,
speaker, synthetic) compatible with evals.benchmark_voice.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import threading
import wave
from typing import Any, Callable, Optional

import numpy as np

from agent.voice import DEFAULT_SAMPLERATE, record_audio_push_to_talk


def save_pcm_mono_16k_wav(wav_path: Path, samples: np.ndarray, sample_rate: int = DEFAULT_SAMPLERATE) -> float:
    """Save 1D int16/float32 PCM samples as 16 kHz mono WAV and return duration in seconds."""
    arr = np.asarray(samples)
    if arr.ndim > 1:
        arr = arr[:, 0]
    if arr.dtype != np.int16:
        arr = np.clip(arr, -1.0, 1.0)
        arr = (arr * 32767.0).astype(np.int16)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(arr.tobytes())
    return round(len(arr) / float(sample_rate), 3)


def append_manifest_row(
    manifest_path: Path,
    wav_path: Path,
    reference_text: str,
    category: str,
    speaker: str,
    synthetic: bool = False,
) -> dict[str, Any]:
    """Append a normalized JSONL manifest row and return the written dict."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "wav_path": str(wav_path).replace("\\", "/"),
        "reference_text": reference_text,
        "category": category,
        "speaker": speaker,
        "synthetic": bool(synthetic),
    }
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def run_recording_session(
    prompts_path: Path,
    out_dir: Path,
    speaker: str,
    manifest_path: Optional[Path] = None,
    record_fn: Optional[Callable[[threading.Event, int], Any]] = None,
    input_fn: Callable[[str], str] = input,
    max_prompts: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Guide a human speaker through prompts one by one and write 16 kHz mono WAVs + manifest."""
    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    if max_prompts is not None:
        prompts = prompts[: max(1, max_prompts)]

    target_manifest = manifest_path or (out_dir / "manifest.jsonl")
    recorder = record_fn or record_audio_push_to_talk
    written: list[dict[str, Any]] = []

    for idx, item in enumerate(prompts, start=1):
        pid = item.get("id") or f"clip_{idx:03d}"
        cat = item.get("category") or "general"
        text = item["text"]
        print(f"\n[{idx}/{len(prompts)}] ({cat}) {pid}")
        print(f"Prompt: {text}")
        cmd = input_fn("Press ENTER to start recording (or type 's' to skip, 'q' to quit): ").strip().lower()
        if cmd == "q":
            break
        if cmd == "s":
            continue

        stop_event = threading.Event()
        holder: dict[str, Any] = {"audio": None}

        def _worker():
            holder["audio"] = recorder(stop_event, DEFAULT_SAMPLERATE)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        input_fn("Recording... Press ENTER to stop.")
        stop_event.set()
        t.join(timeout=10.0)

        audio = holder["audio"]
        if audio is None or getattr(audio, "size", 0) == 0:
            print("Empty recording skipped.")
            continue

        wav_file = out_dir / f"{speaker}_{pid}.wav"
        dur_s = save_pcm_mono_16k_wav(wav_file, audio, DEFAULT_SAMPLERATE)
        row = append_manifest_row(
            manifest_path=target_manifest,
            wav_path=wav_file,
            reference_text=text,
            category=cat,
            speaker=speaker,
            synthetic=False,
        )
        row["duration_s"] = dur_s
        written.append(row)
        print(f"Saved {wav_file} ({dur_s}s)")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Record 16 kHz mono WAV test clips from a prompt script.")
    parser.add_argument("--prompts", type=Path, default=Path("bench_clips/prompts.json"), help="Prompt script JSON file.")
    parser.add_argument("--out-dir", type=Path, default=Path("bench_clips/human"), help="Output WAV directory.")
    parser.add_argument("--manifest", type=Path, default=None, help="Output manifest JSONL path (default: <out-dir>/manifest.jsonl).")
    parser.add_argument("--speaker", type=str, default="speaker1", help="Speaker label stored in manifest.")
    parser.add_argument("--max-prompts", type=int, default=None, help="Optional cap on number of prompts.")
    args = parser.parse_args()

    rows = run_recording_session(
        prompts_path=args.prompts,
        out_dir=args.out_dir,
        speaker=args.speaker,
        manifest_path=args.manifest,
        max_prompts=args.max_prompts,
    )
    print(f"Recorded {len(rows)} clip(s).")


if __name__ == "__main__":
    main()
