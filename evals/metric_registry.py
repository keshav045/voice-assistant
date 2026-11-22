"""Central Metric Registry for Nexus AI Evaluation Suite.

Defines mathematical calculation methods for:
- Retrieval metrics (Hit@k, MRR, NDCG)
- Latency percentiles (p50, p90, p95, p99)
- Token cost estimation ($ / 1k tokens)
- Leakage, Safety, and Toxicity compliance rates
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence


def compute_hit_at_k(retrieved: Sequence[str], ground_truth: str, k: int = 3) -> bool:
    """Check if ground truth item is present in top-k retrieved items."""
    return ground_truth in list(retrieved)[:k]


def compute_mrr(ranks: Sequence[Optional[int]]) -> float:
    """Calculate Mean Reciprocal Rank (MRR)."""
    if not ranks:
        return 0.0
    reciprocals = [1.0 / r if r and r > 0 else 0.0 for r in ranks]
    return float(sum(reciprocals) / len(reciprocals))


def compute_ndcg_at_k(retrieved: Sequence[str], ground_truth: str, k: int = 3) -> float:
    """Calculate Normalized Discounted Cumulative Gain (NDCG@k) for binary relevance."""
    top_k = list(retrieved)[:k]
    if ground_truth not in top_k:
        return 0.0
    rank = top_k.index(ground_truth) + 1
    dcg = 1.0 / math.log2(rank + 1)
    idcg = 1.0 / math.log2(2)  # Ideal rank is 1
    return float(dcg / idcg)


def compute_percentiles(latencies: Sequence[float]) -> Dict[str, float]:
    """Compute min, avg, max, p50, p90, p95, and p99 from a latency series in ms."""
    if not latencies:
        return {"min": 0.0, "avg": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    s = sorted(latencies)
    n = len(s)

    def p(pct: float) -> float:
        idx = max(0, min(n - 1, int(math.ceil(pct / 100.0 * n)) - 1))
        return s[idx]

    return {
        "min": round(s[0], 2),
        "avg": round(sum(s) / n, 2),
        "p50": round(p(50), 2),
        "p90": round(p(90), 2),
        "p95": round(p(95), 2),
        "p99": round(p(99), 2),
        "max": round(s[-1], 2),
    }


def compute_cost_estimate(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "gpt-4o",
) -> Dict[str, Any]:
    """Estimate inference cost in USD for given token consumption."""
    # Pricing per 1M tokens (Standard 2026 tiers)
    pricing = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "qwen2.5:1.5b": {"input": 0.0, "output": 0.0},        # Local Ollama
    }
    rates = pricing.get(model, pricing["gpt-4o"])
    input_cost = (prompt_tokens / 1_000_000) * rates["input"]
    output_cost = (completion_tokens / 1_000_000) * rates["output"]
    total_cost = input_cost + output_cost

    return {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_cost_usd": round(total_cost, 6),
        "is_local_free": rates["input"] == 0.0,
    }


class MetricRegistry:
    """Registry for recording, scoring, and summarizing test suite metrics."""

    def __init__(self):
        self.metrics: Dict[str, Any] = {}

    def record(self, module: str, name: str, value: Any, passed: bool, details: str = ""):
        if module not in self.metrics:
            self.metrics[module] = []
        self.metrics[module].append({
            "name": name,
            "value": value,
            "passed": passed,
            "details": details,
        })

    def summary(self) -> Dict[str, Any]:
        total_tests = sum(len(items) for items in self.metrics.values())
        passed_tests = sum(sum(1 for i in items if i["passed"]) for items in self.metrics.values())
        pass_rate = round((passed_tests / total_tests) * 100, 1) if total_tests else 0.0

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "pass_rate_pct": pass_rate,
            "modules": {m: {"count": len(items), "passed": sum(1 for i in items if i["passed"])} for m, items in self.metrics.items()},
        }
