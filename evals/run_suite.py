"""Master Evaluation Suite Orchestrator.

Runs all modular evaluation modules:
1. Retriever & Semantic Memory
2. Reranker Precision
3. Generator & Clean Speech
4. Latency Profiling
5. Cost Estimation & Free Tier
6. Leakage & Boundary Protection
7. System Ops & Concurrency
8. RAG Pipeline
9. Error Reliability & Recovery
10. Safety & Confirmation Gating
11. Scope & Domain Boundaries
12. Toxicity & Profanity Defense
13. Application & Session Management
14. Promotion Quality Gate
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from evals.harness import EvalHarness
from evals.eval_retriever import run_retriever_eval
from evals.eval_retriever_with_reranker import run_reranker_eval
from evals.eval_generator import run_generator_eval
from evals.eval_latency import run_latency_eval
from evals.eval_cost import run_cost_eval
from evals.eval_leakage import run_leakage_eval
from evals.eval_ops import run_ops_eval
from evals.eval_rag_pipeline import run_rag_pipeline_eval
from evals.eval_reliability import run_reliability_eval
from evals.eval_safety import run_safety_eval
from evals.eval_scope import run_scope_eval
from evals.eval_toxicity import run_toxicity_eval
from evals.eval_application import run_application_eval
from evals.promote import check_promotion_readiness


def run_full_suite() -> Dict[str, Any]:
    print("=" * 80)
    print("  NEXUS AI ASSISTANT — MASTER MODULAR EVALUATION SUITE")
    print("=" * 80)
    print()

    harness = EvalHarness(name="NexusMasterSuite")

    modules = [
        ("Retrieval & Memory", run_retriever_eval),
        ("Reranker Two-Stage", run_reranker_eval),
        ("Speech Generation", run_generator_eval),
        ("Latency Profiling", run_latency_eval),
        ("Cost & Budgeting", run_cost_eval),
        ("Leakage Protection", run_leakage_eval),
        ("Infrastructure Ops", run_ops_eval),
        ("End-to-End RAG", run_rag_pipeline_eval),
        ("Error Reliability", run_reliability_eval),
        ("Safety Gating", run_safety_eval),
        ("Domain Scope", run_scope_eval),
        ("Toxicity Defense", run_toxicity_eval),
        ("Application Session", run_application_eval),
    ]

    for label, fn in modules:
        print(f"--- Running {label} ---")
        with harness.timer(label):
            fn(harness)
        print()

    # Export reports
    out_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(out_dir, "suite_report.json")
    report = harness.export_report(output_path=json_path)

    summary = report["summary"]
    print("=" * 80)
    print(f"  TOTAL TESTS: {summary['total_tests']} | PASSED: {summary['passed_tests']} | FAILED: {summary['failed_tests']}")
    print(f"  OVERALL SUITE SCORE: {summary['pass_rate_pct']}% PASS")
    print("=" * 80)
    print()

    # Promotion Gate
    promoted = check_promotion_readiness(report)

    return report


if __name__ == "__main__":
    report = run_full_suite()
    sys.exit(0 if report["summary"]["failed_tests"] == 0 else 1)
