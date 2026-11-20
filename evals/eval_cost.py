"""Evaluates token usage, API budget cost estimation, and local model free tier savings."""

import os
import sys
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from evals.metric_registry import compute_cost_estimate
from evals.harness import EvalHarness


def run_cost_eval(harness: EvalHarness) -> Dict[str, Any]:
    # Typical query: ~250 prompt tokens (system + history), ~60 output tokens
    cloud_cost = compute_cost_estimate(prompt_tokens=250, completion_tokens=60, model="gpt-4o")
    local_cost = compute_cost_estimate(prompt_tokens=250, completion_tokens=60, model="rtu-senior:latest")

    daily_turns = 100
    cloud_daily = round(cloud_cost["estimated_cost_usd"] * daily_turns, 4)
    local_daily = round(local_cost["estimated_cost_usd"] * daily_turns, 4)

    harness.record_test("eval_cost", "Cloud Model Budget", cloud_cost["estimated_cost_usd"] < 0.01, cloud_cost["estimated_cost_usd"], f"${cloud_cost['estimated_cost_usd']}/turn (GPT-4o)")
    harness.record_test("eval_cost", "Local Model Free Tier", local_cost["is_local_free"] is True, local_daily, f"$0.00/turn (Local Ollama rtu-senior)")

    return {
        "cloud_per_turn_usd": cloud_cost["estimated_cost_usd"],
        "cloud_100_turns_usd": cloud_daily,
        "local_per_turn_usd": local_cost["estimated_cost_usd"],
        "local_100_turns_usd": local_daily,
        "cost_savings_pct": 100.0,
    }


if __name__ == "__main__":
    h = EvalHarness()
    run_cost_eval(h)
