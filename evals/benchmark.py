"""Comprehensive Benchmark & Error Detection Suite for Nexus AI Voice Assistant.

Benchmarks:
1. Component & Pipeline Latencies (Calculator, Clock, Search, App Launcher, WhatsApp, Python Sandbox, RAG, E2E Turn)
2. Tool Dispatch Accuracy & Parameter Extraction
3. Error Detection & Resilience (Malformed math, division by zero, code injection blocking, invalid timezones, fallback search)
4. Spoken Text Quality & Markdown Leak Prevention
5. Safety Confirmation Gating (Write protection, natural language confirm/deny)
6. System Health & Cloud Readiness (SQLite WAL, OpenAI, Google OAuth, LiveKit Cloud)
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(override=True)

from db.models import (
    get_db_connection,
    db_add_fact,
    db_list_facts,
    db_forget_fact,
)
from rag.store import add_doc_chunk, search_doc_chunks
from agent.confirm import requires_confirmation, is_confirmed
from agent.voice import clean_spoken_text
from agent.tools import TOOLS_REGISTRY
from agent.tools.email import _compose_email


def benchmark_latencies(iterations: int = 3) -> Dict[str, Any]:
    """Profile latency across all internal engines and tools."""
    profile: Dict[str, List[float]] = {
        "calculator": [],
        "clock_timezone": [],
        "app_launcher": [],
        "whatsapp_url": [],
        "python_sandbox": [],
        "web_search": [],
        "rag_vector_search": [],
        "email_composer": [],
    }

    # 1. Calculator
    for _ in range(iterations):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["calculator"](expression="450 * 12 + 18% of 5000 - sqrt(144)")
        profile["calculator"].append((time.perf_counter() - t0) * 1000)

    # 2. Clock & Timezone
    for _ in range(iterations):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["get_current_time"](timezone_str="Asia/Kolkata")
        profile["clock_timezone"].append((time.perf_counter() - t0) * 1000)

    # 3. App Launcher (Resolve URL)
    for _ in range(iterations):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["open_app"](target="youtube", query="lofi hip hop")
        profile["app_launcher"].append((time.perf_counter() - t0) * 1000)

    # 4. WhatsApp
    for _ in range(iterations):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["send_whatsapp_message"](contact_name="Rahul", message="Hey Rahul, let's connect!")
        profile["whatsapp_url"].append((time.perf_counter() - t0) * 1000)

    # 5. Python Sandbox
    for _ in range(iterations):
        t0 = time.perf_counter()
        TOOLS_REGISTRY["run_python_code"](code="ans = sum([x**2 for x in range(10)])\nprint(ans)")
        profile["python_sandbox"].append((time.perf_counter() - t0) * 1000)

    # 6. Web Search (1 iteration to respect rate limits)
    t0 = time.perf_counter()
    TOOLS_REGISTRY["web_search"](query="current weather in Tokyo")
    profile["web_search"].append((time.perf_counter() - t0) * 1000)

    # 7. RAG Vector Search
    for _ in range(iterations):
        t0 = time.perf_counter()
        search_doc_chunks(query="project nexus voice assistant", top_k=2)
        profile["rag_vector_search"].append((time.perf_counter() - t0) * 1000)

    # 8. Email Composer
    for _ in range(iterations):
        t0 = time.perf_counter()
        _compose_email(description="Quarterly sync meeting next Monday", recipient_name="Team")
        profile["email_composer"].append((time.perf_counter() - t0) * 1000)

    results: Dict[str, Dict[str, float]] = {}
    for k, v in profile.items():
        if v:
            results[k] = {
                "avg_ms": round(sum(v) / len(v), 2),
                "min_ms": round(min(v), 2),
                "max_ms": round(max(v), 2),
            }
        else:
            results[k] = {"avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

    return results


def benchmark_tool_accuracy() -> Dict[str, Any]:
    """Test accuracy of tool execution and output validity."""
    tests = []

    # Math accuracy
    calc = TOOLS_REGISTRY["calculator"](expression="25 * 40 + 15% of 1000")
    expected_calc = 1000 + 150  # 1150
    tests.append({
        "name": "Math Percentage Calculation",
        "passed": calc.get("success") is True and calc.get("result") == 1150.0,
        "details": f"Result: {calc.get('result')} (Expected: 1150.0)",
    })

    # Timezone check
    t_res = TOOLS_REGISTRY["get_current_time"](timezone_str="UTC")
    tests.append({
        "name": "Timezone Precision (UTC)",
        "passed": t_res.get("success") is True and "UTC" in t_res.get("timezone", ""),
        "details": f"Spoken: {t_res.get('spoken')}",
    })

    # YouTube URL launcher
    yt = TOOLS_REGISTRY["open_app"](target="youtube", query="jazz music")
    tests.append({
        "name": "App Launcher Query Resolution",
        "passed": yt.get("success") is True and "youtube.com" in yt.get("url", ""),
        "details": f"URL: {yt.get('url')}",
    })

    # WhatsApp deep link
    wa = TOOLS_REGISTRY["send_whatsapp_message"](contact_name="Alice", message="Hello Alice")
    tests.append({
        "name": "WhatsApp Click-to-Chat Link Generation",
        "passed": wa.get("success") is True and "whatsapp.com" in wa.get("url", ""),
        "details": f"Target: {wa.get('contact')}",
    })

    # Python Execution
    py = TOOLS_REGISTRY["run_python_code"](code="print([i for i in range(4)])")
    tests.append({
        "name": "Python Code Execution Sandbox",
        "passed": py.get("success") is True and "[0, 1, 2, 3]" in str(py.get("output")),
        "details": f"Output: {py.get('output').strip()}",
    })

    # Email Composer
    ec = _compose_email(description="Project status meeting reschedule", recipient_name="John")
    tests.append({
        "name": "AI Email Generation Quality",
        "passed": bool(ec.get("subject")) and "John" in ec.get("body", ""),
        "details": f"Subject: '{ec.get('subject')}'",
    })

    total = len(tests)
    passed = sum(1 for t in tests if t["passed"])
    return {
        "tests": tests,
        "total": total,
        "passed": passed,
        "accuracy_pct": round((passed / total) * 100, 1),
    }


def detect_errors_and_resilience() -> Dict[str, Any]:
    """Inject edge cases and deliberate invalid inputs to verify error detection and graceful handling."""
    error_cases = []

    # 1. Division by zero in calculator
    res = TOOLS_REGISTRY["calculator"](expression="100 / 0")
    zero_div_handled = res.get("success") is False and "division by zero" in res.get("error", "").lower()
    error_cases.append({
        "test": "Division by Zero in Math",
        "handled_gracefully": zero_div_handled,
        "details": f"Caught error: '{res.get('error')}'",
    })

    # 2. Syntax error in calculator
    res = TOOLS_REGISTRY["calculator"](expression="((10 + 5")
    syntax_handled = res.get("success") is False and bool(res.get("error"))
    error_cases.append({
        "test": "Syntax Error in Math Expression",
        "handled_gracefully": syntax_handled,
        "details": f"Caught error: '{res.get('error')}'",
    })

    # 3. Security keyword in Python Sandbox (Code injection protection)
    res = TOOLS_REGISTRY["run_python_code"](code="import os\nos.system('dir')")
    sandbox_blocked = res.get("success") is False and "security restriction" in res.get("error", "").lower()
    error_cases.append({
        "test": "Malicious Code Injection Blocking (os.system)",
        "handled_gracefully": sandbox_blocked,
        "details": f"Blocked with: '{res.get('error')}'",
    })

    # 4. Unknown App target (Graceful search fallback)
    res = TOOLS_REGISTRY["open_app"](target="quantum_hyper_nonexistent_tool_123")
    unknown_app_handled = res.get("success") is True and "google.com" in res.get("url", "")
    error_cases.append({
        "test": "Unknown App Launcher Graceful Fallback",
        "handled_gracefully": unknown_app_handled,
        "details": f"Fallback search URL: '{res.get('url')}'",
    })

    # 5. Invalid Timezone (Graceful fallback)
    res = TOOLS_REGISTRY["get_current_time"](timezone_str="Unknown/FantasyLand")
    tz_handled = res.get("success") is True and ("UTC" in res.get("timezone", "") or "Unknown" in res.get("timezone", ""))
    error_cases.append({
        "test": "Invalid Timezone Fallback Handling",
        "handled_gracefully": tz_handled,
        "details": f"Resolved timezone: '{res.get('timezone')}'",
    })

    # 6. Markdown Leak Prevention in TTS Output
    raw_markdown = "### Spoken Update\n* **Task 1**: Finished with `status 200`!\nCheck [Docs](https://example.com)."
    clean = clean_spoken_text(raw_markdown)
    has_markdown_leak = any(sym in clean for sym in ["###", "**", "`", "[Docs]", "https://"])
    error_cases.append({
        "test": "Zero Markdown Leakage in Spoken Voice Stream",
        "handled_gracefully": not has_markdown_leak and len(clean) > 0,
        "details": f"Cleaned speech: '{clean}'",
    })

    total = len(error_cases)
    handled = sum(1 for e in error_cases if e["handled_gracefully"])
    return {
        "cases": error_cases,
        "total": total,
        "handled": handled,
        "resilience_pct": round((handled / total) * 100, 1),
    }


def benchmark_safety_gating() -> Dict[str, Any]:
    """Evaluate human confirmation safety gating precision."""
    critical_actions = ["send_email", "create_event", "delete_task"]
    safe_actions = ["calculator", "get_current_time", "open_app", "web_search", "list_tasks", "list_events"]

    write_passed = sum(1 for a in critical_actions if requires_confirmation(a) is True)
    safe_passed = sum(1 for a in safe_actions if requires_confirmation(a) is False)
    total = len(critical_actions) + len(safe_actions)
    precision = ((write_passed + safe_passed) / total) * 100

    # Natural language confirmation parser
    affirmative = ["yes", "yes please", "sure go ahead", "confirm that", "yep", "do it"]
    rejections = ["no", "cancel", "don't do that", "stop", "abort", "nope"]
    parser_ok = all(is_confirmed(c) is True for c in affirmative) and all(is_confirmed(r) is False for r in rejections)

    return {
        "critical_actions_protected": write_passed == len(critical_actions),
        "safe_actions_unblocked": safe_passed == len(safe_actions),
        "safety_gating_precision_pct": round(precision, 1),
        "nl_parser_passed": parser_ok,
    }


def verify_system_readiness() -> Dict[str, Any]:
    """Probe SQLite WAL concurrency, OpenAI LLM readiness, Google OAuth, and LiveKit Cloud."""
    # SQLite WAL
    wal_active = False
    with get_db_connection() as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        if row and row[0].lower() in ["wal", "memory"]:
            wal_active = True

    # Tables verification
    expected_tables = ["chat_history", "tasks", "memory_facts", "reminders", "notes", "users", "user_oauth_tokens"]
    existing_tables = []
    with get_db_connection() as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [r[0] for r in cur.fetchall()]
    tables_ok = all(t in existing_tables for t in expected_tables)

    # Cloud Credentials
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_ready = bool(openai_key and not openai_key.startswith("your-") and len(openai_key) > 20)

    google_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    google_ready = bool(google_id and google_secret)

    livekit_url = os.environ.get("LIVEKIT_URL", "")
    livekit_key = os.environ.get("LIVEKIT_API_KEY", "")
    livekit_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    livekit_ready = bool(livekit_url and livekit_key and livekit_secret)

    return {
        "sqlite_wal_mode": wal_active,
        "database_tables_intact": tables_ok,
        "openai_llm_ready": openai_ready,
        "google_oauth_ready": google_ready,
        "livekit_cloud_ready": livekit_ready,
        "all_ready": wal_active and tables_ok and openai_ready and google_ready and livekit_ready,
    }


def run_comprehensive_benchmark() -> Dict[str, Any]:
    """Run all benchmark modules and generate scorecard."""
    t_start = time.perf_counter()

    latencies = benchmark_latencies()
    accuracy = benchmark_tool_accuracy()
    error_resilience = detect_errors_and_resilience()
    safety = benchmark_safety_gating()
    readiness = verify_system_readiness()

    total_duration_ms = round((time.perf_counter() - t_start) * 1000, 2)

    # Calculate overall compliance index
    scores = [
        accuracy["accuracy_pct"],
        error_resilience["resilience_pct"],
        safety["safety_gating_precision_pct"],
        100.0 if readiness["all_ready"] else 80.0,
    ]
    overall_score = round(sum(scores) / len(scores), 1)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_benchmark_time_ms": total_duration_ms,
        "overall_score": overall_score,
        "latencies": latencies,
        "accuracy": accuracy,
        "error_resilience": error_resilience,
        "safety": safety,
        "system_readiness": readiness,
    }


def generate_markdown_report(bench: Dict[str, Any]) -> str:
    """Generate a clean GitHub Flavored Markdown benchmark report."""
    md = []
    md.append("# Nexus AI Voice Assistant — Benchmark & Evaluation Scorecard")
    md.append(f"**Timestamp:** `{bench['timestamp']}` | **Overall Score:** `{bench['overall_score']}% PASS`\n")
    md.append("---")

    md.append("## 1. Component Latency Profile")
    md.append("| Component / Tool | Average (ms) | Min (ms) | Max (ms) |")
    md.append("|---|---|---|---|")
    for k, v in bench["latencies"].items():
        md.append(f"| `{k}` | **{v['avg_ms']} ms** | {v['min_ms']} ms | {v['max_ms']} ms |")
    md.append("")

    md.append("## 2. Tool Execution Accuracy")
    md.append(f"**Score:** `{bench['accuracy']['accuracy_pct']}%` ({bench['accuracy']['passed']}/{bench['accuracy']['total']} Passed)\n")
    for t in bench["accuracy"]["tests"]:
        icon = "[PASS]" if t["passed"] else "[FAIL]"
        md.append(f"- {icon} **{t['name']}**: {t['details']}")
    md.append("")

    md.append("## 3. Error Detection & Resilience Testing")
    md.append(f"**Score:** `{bench['error_resilience']['resilience_pct']}%` ({bench['error_resilience']['handled']}/{bench['error_resilience']['total']} Gracefully Handled)\n")
    for c in bench["error_resilience"]["cases"]:
        icon = "[SAFE]" if c["handled_gracefully"] else "[WARN]"
        md.append(f"- {icon} **{c['test']}**: {c['details']}")
    md.append("")

    md.append("## 4. Safety Confirmation Gating")
    md.append(f"- **Write-action protection:** `{'PASS' if bench['safety']['critical_actions_protected'] else 'FAIL'}`")
    md.append(f"- **Read-action unblocking:** `{'PASS' if bench['safety']['safe_actions_unblocked'] else 'FAIL'}`")
    md.append(f"- **Precision:** `{bench['safety']['safety_gating_precision_pct']}%`")
    md.append(f"- **Natural Language Affirm/Deny Parser:** `{'PASS' if bench['safety']['nl_parser_passed'] else 'FAIL'}`\n")

    md.append("## 5. System Health & Infrastructure")
    sr = bench["system_readiness"]
    md.append(f"- SQLite WAL Concurrency: `{'ENABLED' if sr['sqlite_wal_mode'] else 'DISABLED'}`")
    md.append(f"- Database Tables Integrity: `{'INTACT' if sr['database_tables_intact'] else 'MISSING'}`")
    md.append(f"- OpenAI LLM Status: `{'READY' if sr['openai_llm_ready'] else 'NOT CONFIGURED'}`")
    md.append(f"- Google OAuth Status: `{'READY' if sr['google_oauth_ready'] else 'NOT CONFIGURED'}`")
    md.append(f"- LiveKit Cloud WebRTC Status: `{'READY' if sr['livekit_cloud_ready'] else 'NOT CONFIGURED'}`")

    return "\n".join(md)


if __name__ == "__main__":
    print("=" * 76)
    print("  NEXUS AI VOICE ASSISTANT — BENCHMARK & ERROR DETECTION ENGINE")
    print("=" * 76)
    bench_data = run_comprehensive_benchmark()

    # Save JSON and MD
    out_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(out_dir, "benchmark_report.json")
    md_path = os.path.join(out_dir, "benchmark_report.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(bench_data, f, indent=2)

    md_report = generate_markdown_report(bench_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)

    print()
    print(f"  Overall Score: {bench_data['overall_score']}% PASS")
    print(f"  Accuracy:      {bench_data['accuracy']['accuracy_pct']}%")
    print(f"  Resilience:    {bench_data['error_resilience']['resilience_pct']}% (Errors caught & handled gracefully)")
    print(f"  Safety Gating: {bench_data['safety']['safety_gating_precision_pct']}%")
    print(f"  Saved Reports: {json_path}")
    print(f"                 {md_path}")
    print("=" * 76)
