"""Compares benchmark runs (e.g., Cloud OpenAI GPT-4o vs Local Ollama rtu-senior)."""

import json
import os
import sys
from typing import Any, Dict, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def compare_runs(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a side-by-side comparison between two benchmark runs."""
    score_a = run_a.get("summary", {}).get("pass_rate_pct", 0.0)
    score_b = run_b.get("summary", {}).get("pass_rate_pct", 0.0)

    comparison = {
        "run_a_score": score_a,
        "run_b_score": score_b,
        "score_delta": round(score_b - score_a, 1),
        "winner": "Run B" if score_b > score_a else ("Run A" if score_a > score_b else "Tie"),
    }

    print("=" * 60)
    print("  EVALUATION RUN COMPARISON")
    print("=" * 60)
    print(f"  Run A Pass Rate: {score_a}%")
    print(f"  Run B Pass Rate: {score_b}%")
    print(f"  Delta:           {comparison['score_delta']}%")
    print(f"  Result:          {comparison['winner']}")
    print("=" * 60)

    return comparison


if __name__ == "__main__":
    mock_a = {"summary": {"pass_rate_pct": 100.0}}
    mock_b = {"summary": {"pass_rate_pct": 100.0}}
    compare_runs(mock_a, mock_b)
