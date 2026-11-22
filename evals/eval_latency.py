"""Evaluates component execution and response latency profiles."""

import os
import sys
import time
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from agent.tools import TOOLS_REGISTRY
from evals.metric_registry import compute_percentiles
from evals.harness import EvalHarness


def run_latency_eval(harness: EvalHarness) -> Dict[str, Any]:
    profile = {}

    # 1. Calculator latency (multiple iterations)
    calc_times = []
    for _ in range(5):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["calculator"](expression="450 * 12 + 18% of 5000 - sqrt(144)")
        calc_times.append((time.perf_counter() - t0) * 1000)
    profile["calculator"] = compute_percentiles(calc_times)

    # 2. Clock tool latency
    clock_times = []
    for _ in range(5):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["get_current_time"](timezone_str="UTC")
        clock_times.append((time.perf_counter() - t0) * 1000)
    profile["clock"] = compute_percentiles(clock_times)

    # 3. Python sandbox latency
    py_times = []
    for _ in range(3):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["run_python_code"](code="sum([x**2 for x in range(20)])")
        py_times.append((time.perf_counter() - t0) * 1000)
    profile["python_sandbox"] = compute_percentiles(py_times)

    # 4. App launcher resolution latency
    app_times = []
    for _ in range(3):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["open_app"](name="youtube", query="lofi beats")
        app_times.append((time.perf_counter() - t0) * 1000)
    profile["app_launcher"] = compute_percentiles(app_times)

    calc_fast = profile["calculator"]["p95"] < 10.0
    clock_fast = profile["clock"]["p95"] < 25.0
    py_fast = profile["python_sandbox"]["p95"] < 150.0

    harness.record_test("eval_latency", "Math Calculator Latency", calc_fast, profile["calculator"]["avg"], f"p95: {profile['calculator']['p95']}ms (target <10ms)")
    harness.record_test("eval_latency", "Clock Latency", clock_fast, profile["clock"]["avg"], f"p95: {profile['clock']['p95']}ms (target <25ms)")
    harness.record_test("eval_latency", "Python Sandbox Latency", py_fast, profile["python_sandbox"]["avg"], f"p95: {profile['python_sandbox']['p95']}ms (target <150ms)")

    return profile


if __name__ == "__main__":
    h = EvalHarness()
    run_latency_eval(h)
