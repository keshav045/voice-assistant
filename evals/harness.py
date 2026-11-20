"""Execution Harness for the Nexus AI Evaluation Suite.

Provides unified logging, timing context managers, assertion handlers,
and scorecard persistence.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from evals.metric_registry import MetricRegistry


class EvalHarness:
    """Core evaluation harness managing runs across all modular test suites."""

    def __init__(self, name: str = "NexusEvalHarness"):
        self.name = name
        self.registry = MetricRegistry()
        self.timings: Dict[str, float] = {}

    @contextlib.contextmanager
    def timer(self, label: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.timings[label] = round(elapsed_ms, 2)

    def record_test(self, module: str, name: str, passed: bool, value: Any = None, details: str = ""):
        self.registry.record(module=module, name=name, value=value, passed=passed, details=details)
        status_icon = "[PASS] PASS" if passed else "[FAIL] FAIL"
        print(f"  [{status_icon}] {module:24} | {name:30} | {details}")

    def export_report(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        report = {
            "harness": self.name,
            "timestamp": time.time(),
            "summary": self.registry.summary(),
            "metrics": self.registry.metrics,
            "timings": self.timings,
        }
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        return report
