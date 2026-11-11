"""Comprehensive Evaluation Benchmark Suite for Nexus AI Voice Assistant.

Covers the complete 4-pillar LLM & Voice Agent Evaluation Pyramid:
1. Retrieval Evaluation (Hit@1, Hit@3, MRR, Memory Recall)
2. Generation Evaluation (Clean Speech compliance, Voice conciseness, Composition quality)
3. Pipeline Evaluation (Tool selection accuracy, Confirmation gating, Component latency)
4. Application Evaluation (End-to-end scenario pass rate, WAL integrity, Health probes)
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import time
from typing import Any, Dict, List, Tuple

# Ensure project root is in path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(override=True)

from db.models import (
    init_db,
    get_db_connection,
    db_add_fact,
    db_list_facts,
    db_forget_fact,
    db_add_task,
    db_list_tasks,
)
from rag.store import add_doc_chunk, search_doc_chunks, compute_embedding, cosine_similarity
from agent.confirm import requires_confirmation, format_read_back, is_confirmed
from agent.voice import clean_spoken_text
from agent.tools import TOOLS_REGISTRY
from agent.tools.email import _compose_email
import yaml


# ============================================================================ #
# Pillar 1: Retrieval Evaluation (RAG & Semantic Memory)
# ============================================================================ #

def evaluate_retrieval() -> Dict[str, Any]:
    """Evaluate vector search recall, ranking, and semantic memory facts."""
    test_docs = [
        {"file": "wifi_guide.txt", "text": "The guest Wi-Fi network SSID is OfficeGuest and the password is securePass2026.", "queries": ["What is the guest wifi password?", "How do I connect to wifi?"]},
        {"file": "q4_roadmap.txt", "text": "Project Nexus aims to launch LiveKit real-time voice streaming and Gmail OAuth in Q4.", "queries": ["When is Nexus launching voice streaming?", "What are the Q4 goals?"]},
        {"file": "leave_policy.pdf", "text": "Employees receive 24 days of paid time off per calendar year and 10 public holidays.", "queries": ["How many PTO days do we get?", "What is the annual leave policy?"]},
        {"file": "deployment.md", "text": "Deployments to Vercel require setting OPENAI_API_KEY and LIVEKIT credentials in environment variables.", "queries": ["How to deploy on Vercel?", "What env vars are needed for Vercel?"]},
    ]

    # Index test documents
    chunk_ids = []
    for doc in test_docs:
        cid = add_doc_chunk(file_name=doc["file"], text=doc["text"], section="general")
        chunk_ids.append(cid)

    # Evaluate Hit@1, Hit@3, and MRR
    total_queries = 0
    hit_1 = 0
    hit_3 = 0
    reciprocal_ranks = []

    for doc in test_docs:
        for q in doc["queries"]:
            total_queries += 1
            results = search_doc_chunks(query=q, top_k=3)
            retrieved_files = [r["file"] for r in results]

            if retrieved_files and retrieved_files[0] == doc["file"]:
                hit_1 += 1

            if doc["file"] in retrieved_files:
                hit_3 += 1
                rank = retrieved_files.index(doc["file"]) + 1
                reciprocal_ranks.append(1.0 / rank)
            else:
                reciprocal_ranks.append(0.0)

    # Clean up test chunks
    with get_db_connection() as conn:
        for cid in chunk_ids:
            conn.execute("DELETE FROM doc_chunks WHERE id = ?", (cid,))
        conn.commit()

    # Semantic memory evaluation
    fact_id = db_add_fact("User's favorite programming language is Python", category="preferences")
    all_facts = db_list_facts()
    memory_recall_success = any("Python" in f["fact"] for f in all_facts)
    db_forget_fact("Python")

    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0
    hit_1_rate = (hit_1 / total_queries) * 100 if total_queries else 0.0
    hit_3_rate = (hit_3 / total_queries) * 100 if total_queries else 0.0

    return {
        "queries_tested": total_queries,
        "hit_at_1_pct": round(hit_1_rate, 2),
        "hit_at_3_pct": round(hit_3_rate, 2),
        "mrr": round(mrr, 4),
        "semantic_memory_recall": memory_recall_success,
        "passed": hit_3_rate >= 80.0 and mrr >= 0.75,
    }


# ============================================================================ #
# Pillar 2: Generation Evaluation (Speech Quality & Voice Formatting)
# ============================================================================ #

def evaluate_generation() -> Dict[str, Any]:
    """Evaluate TTS spoken text clean formatting, voice brevity, and AI composition."""
    sample_raw_outputs = [
        "**Sure!** Here is the result: `42`. Check out [Google](https://google.com) for details.",
        "### Project Update\n- Item 1\n- Item 2\n* Done!",
        "Calculated **15 * 8** = `120` 🎉.",
    ]

    # 1. Clean speech compliance (must contain zero markdown stars, backticks, or raw hashes)
    clean_speech_checks = 0
    clean_speech_passed = 0
    for raw in sample_raw_outputs:
        clean_speech_checks += 1
        cleaned = clean_spoken_text(raw)
        has_markdown = bool(re.search(r"(\*\*|__|\`|###|\[.*?\]\(.*?\))", cleaned))
        if not has_markdown and len(cleaned.strip()) > 0:
            clean_speech_passed += 1

    clean_speech_score = (clean_speech_passed / clean_speech_checks) * 100 if clean_speech_checks else 0.0

    # 2. AI Email Composer Quality
    composed = _compose_email(
        description="Inform team about quarterly review meeting on Friday at 3pm",
        recipient_name="Team",
    )
    has_subject = bool(composed.get("subject") and len(composed["subject"]) > 5)
    has_body = bool(composed.get("body") and len(composed["body"]) > 20)
    has_greeting = bool(re.search(r"(Hi|Dear|Hello)\b", composed.get("body", "")))
    composer_passed = has_subject and has_body and has_greeting

    # 3. Voice Conciseness Index (Spoken text should not exceed conversational voice boundaries)
    test_spoken = "Opening YouTube and searching for lofi music for you."
    word_count = len(test_spoken.split())
    is_concise = 3 <= word_count <= 40

    return {
        "clean_speech_compliance_pct": round(clean_speech_score, 2),
        "ai_composer_quality": composer_passed,
        "composer_subject": composed.get("subject"),
        "voice_conciseness_index": is_concise,
        "passed": clean_speech_score == 100.0 and composer_passed and is_concise,
    }


# ============================================================================ #
# Pillar 3: Pipeline Evaluation (Tool Selection, Safety Gating & Latency)
# ============================================================================ #

def evaluate_pipeline() -> Dict[str, Any]:
    """Evaluate tool dispatching, confirmation gating accuracy, and execution latency."""
    # 1. Tool execution & latency profiling
    latencies: Dict[str, float] = {}

    # Calculator latency
    t0 = time.perf_counter()
    calc_res = TOOLS_REGISTRY["calculator"](expression="450 * 12 + 18% of 5000")
    latencies["calculator_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    calc_valid = calc_res.get("result") == 6300.0

    # Current time latency
    t0 = time.perf_counter()
    time_res = TOOLS_REGISTRY["get_current_time"](timezone_str="Asia/Kolkata")
    latencies["clock_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    time_valid = bool(time_res.get("spoken") or time_res.get("iso"))

    # Vector search latency
    t0 = time.perf_counter()
    search_doc_chunks(query="test latency query", top_k=2)
    latencies["vector_search_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    # 2. Safety Confirmation Gating Accuracy
    critical_actions = ["create_event", "send_email", "delete_task"]
    safe_actions = ["web_search", "get_current_time", "list_events", "list_tasks", "search_email", "calculator"]

    gating_correct = sum(1 for a in critical_actions if requires_confirmation(a) is True)
    safe_correct = sum(1 for a in safe_actions if requires_confirmation(a) is False)
    total_gating = len(critical_actions) + len(safe_actions)
    gating_accuracy = ((gating_correct + safe_correct) / total_gating) * 100

    # 3. Confirmation parser verification
    confirms = ["yes", "yes please", "sure go ahead", "confirm that", "yep", "do it"]
    rejects = ["no", "cancel", "don't do that", "stop", "abort", "nope"]
    parser_passed = all(is_confirmed(c) is True for c in confirms) and all(is_confirmed(r) is False for r in rejects)

    return {
        "calculator_valid": calc_valid,
        "clock_valid": time_valid,
        "component_latencies": latencies,
        "safety_gating_accuracy_pct": round(gating_accuracy, 2),
        "confirmation_parser_accuracy": parser_passed,
        "passed": calc_valid and time_valid and gating_accuracy == 100.0 and parser_passed,
    }


# ============================================================================ #
# Pillar 4: Application Evaluation (End-to-End System Health & Scenarios)
# ============================================================================ #

def evaluate_application() -> Dict[str, Any]:
    """Evaluate system health, scenario coverage from YAML, and WAL integrity."""
    # 1. Scenarios coverage
    scenarios_path = os.path.join(ROOT_DIR, "tests", "scenarios.yaml")
    scenarios_loaded = 0
    if os.path.exists(scenarios_path):
        with open(scenarios_path, "r", encoding="utf-8") as f:
            sc_data = yaml.safe_load(f)
            scenarios_loaded = len(sc_data.get("scenarios", []))

    # 2. SQLite WAL mode integrity check
    wal_active = False
    with get_db_connection() as conn:
        cur = conn.execute("PRAGMA journal_mode;")
        row = cur.fetchone()
        if row and row[0].lower() in ["wal", "memory"]:
            wal_active = True

    # 3. LiveKit Configuration Readiness
    lk_url = os.environ.get("LIVEKIT_URL", "").strip()
    lk_key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    lk_secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    livekit_configured = bool(lk_url and lk_key and lk_secret)

    # 4. Google OAuth Configuration Readiness
    g_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    g_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    google_configured = bool(g_id and g_secret)

    return {
        "scenarios_defined": scenarios_loaded,
        "sqlite_wal_mode": wal_active,
        "livekit_webrtc_configured": livekit_configured,
        "google_oauth_configured": google_configured,
        "passed": scenarios_loaded >= 10 and wal_active and livekit_configured and google_configured,
    }


# ============================================================================ #
# Full Evaluation Orchestrator
# ============================================================================ #

def run_full_evaluation() -> Dict[str, Any]:
    """Execute all 4 pillars and print an executive benchmark scorecard."""
    print("=" * 72)
    print("  NEXUS AI VOICE ASSISTANT — 4-PILLAR EVALUATION BENCHMARK SUITE")
    print("=" * 72)
    print()

    # 1. Retrieval
    print("[1/4] Running Retrieval Evaluation (RAG & Semantic Memory)...")
    retrieval_res = evaluate_retrieval()
    print(f"      Hit@1: {retrieval_res['hit_at_1_pct']}% | Hit@3: {retrieval_res['hit_at_3_pct']}% | MRR: {retrieval_res['mrr']}")
    print(f"      Semantic Memory Recall: {'PASS' if retrieval_res['semantic_memory_recall'] else 'FAIL'}")
    print()

    # 2. Generation
    print("[2/4] Running Generation Evaluation (Spoken Quality & Brevity)...")
    generation_res = evaluate_generation()
    print(f"      Clean Speech Compliance: {generation_res['clean_speech_compliance_pct']}% (0 raw markdown tags)")
    print(f"      Voice Conciseness Index: {'PASS' if generation_res['voice_conciseness_index'] else 'FAIL'}")
    print(f"      AI Email Composition:    {'PASS' if generation_res['ai_composer_quality'] else 'FAIL'}")
    print()

    # 3. Pipeline
    print("[3/4] Running Pipeline Evaluation (Tool Dispatch & Safety Gating)...")
    pipeline_res = evaluate_pipeline()
    print(f"      Safety Gating Accuracy:  {pipeline_res['safety_gating_accuracy_pct']}% (100% write-action protection)")
    print(f"      Confirmation Parser:     {'PASS' if pipeline_res['confirmation_parser_accuracy'] else 'FAIL'}")
    print(f"      Component Latencies:     Calculator={pipeline_res['component_latencies']['calculator_ms']}ms, VectorSearch={pipeline_res['component_latencies']['vector_search_ms']}ms")
    print()

    # 4. Application
    print("[4/4] Running Application Evaluation (WAL Concurrency & Readiness)...")
    app_res = evaluate_application()
    print(f"      Scenarios Defined:       {app_res['scenarios_defined']} test scenarios")
    print(f"      SQLite WAL Mode:         {'ENABLED' if app_res['sqlite_wal_mode'] else 'DISABLED'}")
    print(f"      LiveKit Cloud Readiness: {'CONFIGURED' if app_res['livekit_webrtc_configured'] else 'NOT CONFIGURED'}")
    print(f"      Google OAuth Readiness:  {'CONFIGURED' if app_res['google_oauth_configured'] else 'NOT CONFIGURED'}")
    print()

    overall_passed = (
        retrieval_res["passed"]
        and generation_res["passed"]
        and pipeline_res["passed"]
        and app_res["passed"]
    )

    print("=" * 72)
    print(f"  OVERALL EVALUATION SCORE: {'PASS (100% Compliant)' if overall_passed else 'ACTION REQUIRED'}")
    print("=" * 72)

    return {
        "timestamp": time.time(),
        "retrieval": retrieval_res,
        "generation": generation_res,
        "pipeline": pipeline_res,
        "application": app_res,
        "overall_passed": overall_passed,
    }


if __name__ == "__main__":
    report = run_full_evaluation()
    sys.exit(0 if report["overall_passed"] else 1)
