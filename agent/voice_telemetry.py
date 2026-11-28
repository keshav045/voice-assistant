"""Per-turn voice pipeline telemetry and percentile statistics.

Tracks monotonic turn timings correlated by turn_id / speech_id so latencies
from different turns are never mixed when computing EOU, STT, LLM TTFT,
TTS TTFB, and server-side TTFA.
"""

from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import time
import uuid
from typing import Any, Iterable, Optional


def read_system_resource_snapshot(cpu_sample_interval_s: float = 0.0) -> dict[str, Any]:
    """Capture available RAM, swap/commit usage, process RSS/peak RSS, and CPU load."""
    snap: dict[str, Any] = {}
    if platform.system() == "Windows":
        try:
            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            ms = _MemStatus()
            ms.dwLength = ctypes.sizeof(_MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            snap["ram_total_gb"] = round(ms.ullTotalPhys / (1024**3), 3)
            snap["ram_available_gb"] = round(ms.ullAvailPhys / (1024**3), 3)
            snap["ram_used_pct"] = int(ms.dwMemoryLoad)
            snap["commit_total_gb"] = round(ms.ullTotalPageFile / (1024**3), 3)
            snap["commit_used_gb"] = round((ms.ullTotalPageFile - ms.ullAvailPageFile) / (1024**3), 3)
        except Exception:
            pass

        try:
            class _ProcMemCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = _ProcMemCounters()
            pmc.cb = ctypes.sizeof(_ProcMemCounters)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            k32.K32GetProcessMemoryInfo.restype = ctypes.c_bool
            handle = k32.GetCurrentProcess()
            if k32.K32GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
                snap["process_rss_mb"] = round(pmc.WorkingSetSize / (1024**2), 1)
                snap["process_peak_rss_mb"] = round(pmc.PeakWorkingSetSize / (1024**2), 1)
                snap["process_pagefile_mb"] = round(pmc.PagefileUsage / (1024**2), 1)
        except Exception:
            pass

        if cpu_sample_interval_s > 0:
            try:
                class _FileTime(ctypes.Structure):
                    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]

                def _ft_int(ft: _FileTime) -> int:
                    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

                i1, k1, u1 = _FileTime(), _FileTime(), _FileTime()
                i2, k2, u2 = _FileTime(), _FileTime(), _FileTime()
                if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i1), ctypes.byref(k1), ctypes.byref(u1)):
                    time.sleep(cpu_sample_interval_s)
                    if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i2), ctypes.byref(k2), ctypes.byref(u2)):
                        idle = _ft_int(i2) - _ft_int(i1)
                        total = (_ft_int(k2) - _ft_int(k1)) + (_ft_int(u2) - _ft_int(u1))
                        if total > 0:
                            snap["cpu_load_pct"] = round(max(0.0, min(100.0, (1.0 - idle / total) * 100.0)), 1)
            except Exception:
                pass
    return snap


def default_telemetry_log_path() -> Optional[Path]:
    """Return configured JSONL path for voice turn logs, or None when running tests."""
    explicit = os.environ.get("VOICE_TELEMETRY_LOG", "").strip()
    if explicit.lower() in {"0", "off", "false", "none"}:
        return None
    if explicit:
        return Path(explicit)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    enabled = os.environ.get("VOICE_TELEMETRY_ENABLED", "true").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return None
    return Path("logs") / "voice_turns.jsonl"


def compute_latency_percentiles(values: Iterable[float]) -> dict[str, Optional[float]]:
    """Return count, avg, p50, and p95 rounded to 1 decimal place."""
    nums = sorted(float(v) for v in values if isinstance(v, (int, float)) and v >= 0)
    if not nums:
        return {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None}
    n = len(nums)
    p50_idx = min(n - 1, int(round(0.50 * (n - 1))))
    p95_idx = min(n - 1, int(round(0.95 * (n - 1))))
    return {
        "count": n,
        "avg_ms": round(sum(nums) / n, 1),
        "p50_ms": round(nums[p50_idx], 1),
        "p95_ms": round(nums[p95_idx], 1),
    }


class TurnTimer:
    """Monotonic per-turn timer correlated to a single turn_id / speech_id."""

    def __init__(self, speech_id: Optional[str] = None):
        self.speech_id: str = speech_id or ""
        self.turn_id: str = (speech_id[:8] if speech_id else uuid.uuid4().hex[:8])
        self.marks: dict[str, float] = {}
        self.metrics_ms: dict[str, float] = {}
        self.interrupted: bool = False
        self.error: Optional[str] = None
        self.recorded: bool = False

    def mark(self, name: str, overwrite: bool = False) -> None:
        """Record a monotonic perf_counter mark for a turn lifecycle stage."""
        if overwrite or name not in self.marks:
            self.marks[name] = time.perf_counter()

    def ms(self, start_stage: str, end_stage: str) -> Optional[float]:
        """Return elapsed milliseconds between two recorded stage marks."""
        if start_stage not in self.marks or end_stage not in self.marks:
            return None
        return round((self.marks[end_stage] - self.marks[start_stage]) * 1000.0, 1)

    def set_stage_ms(self, key: str, value_ms: Optional[float]) -> None:
        """Store an explicit SDK-measured latency component (milliseconds) for this turn."""
        if isinstance(value_ms, (int, float)) and value_ms >= 0:
            self.metrics_ms[key] = round(float(value_ms), 1)

    def snapshot(self) -> dict[str, Any]:
        """Build a self-contained single-turn telemetry payload (no cross-turn leakage)."""
        eou_ms = self.metrics_ms.get("eou_ms")
        if eou_ms is None:
            eou_ms = self.ms("speech_end", "endpoint")

        stt_ms = self.metrics_ms.get("stt_ms")
        if stt_ms is None:
            stt_ms = self.ms("endpoint", "stt_final")

        llm_ttft_ms = self.metrics_ms.get("llm_ttft_ms")
        if llm_ttft_ms is None:
            llm_ttft_ms = self.ms("llm_req", "llm_first_token")

        tts_ttfb_ms = self.metrics_ms.get("tts_ttfb_ms")
        if tts_ttfb_ms is None:
            tts_ttfb_ms = self.ms("tts_req", "tts_first_audio")

        server_ttfa_ms = self.ms("speech_end", "tts_first_audio")
        if server_ttfa_ms is None:
            # Derive strictly from components measured within THIS turn_id.
            parts = [v for v in (eou_ms, llm_ttft_ms, tts_ttfb_ms) if isinstance(v, (int, float))]
            if parts and any(k in self.metrics_ms for k in ("llm_ttft_ms", "tts_ttfb_ms")):
                server_ttfa_ms = round(sum(parts), 1)
            elif stt_ms is not None and parts:
                server_ttfa_ms = round(sum(parts) + stt_ms, 1)

        eou_val = round(eou_ms, 1) if isinstance(eou_ms, (int, float)) else 0.0
        stt_val = round(stt_ms, 1) if isinstance(stt_ms, (int, float)) else 0.0
        llm_val = round(llm_ttft_ms, 1) if isinstance(llm_ttft_ms, (int, float)) else 0.0
        tts_val = round(tts_ttfb_ms, 1) if isinstance(tts_ttfb_ms, (int, float)) else 0.0
        ttfa_val = round(server_ttfa_ms, 1) if isinstance(server_ttfa_ms, (int, float)) else 0.0
        mem = read_system_resource_snapshot()
        return {
            "turn_id": self.turn_id,
            "speech_id": self.speech_id or None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint_ms": eou_val,
            "eou_ms": eou_val,
            "stt_final_ms": stt_val,
            "stt_ms": stt_val,
            "llm_ttft_ms": llm_val,
            "tts_ttfb_ms": tts_val,
            "server_ttfa_ms": ttfa_val,
            "ram_available_gb": mem.get("ram_available_gb"),
            "commit_used_gb": mem.get("commit_used_gb"),
            "ram_used_pct": mem.get("ram_used_pct"),
            "interrupted": self.interrupted,
            "error": self.error,
        }

    def record(self, path: Optional[Path | str] = None, extra: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        """Append this turn's correlated metrics row as JSONL when logging is enabled."""
        row = self.snapshot()
        if extra:
            row.update(extra)
        self.recorded = True

        target = Path(path) if path is not None else default_telemetry_log_path()
        if target is None:
            return row
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception:
            pass
        return row
