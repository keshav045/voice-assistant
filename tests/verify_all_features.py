"""Comprehensive Feature Verification Suite for Nexus AI Voice Assistant.
Tests every feature programmatically against the running server and local modules.
"""

import json
import os
import sys
import time
import uuid
import httpx

# Ensure workspace root in path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from db.models import get_db_connection, db_get_user_oauth
from agent.tools import TOOLS_REGISTRY
from agent.confirm import requires_confirmation, is_confirmed
from agent.voice import clean_spoken_text

BASE_URL = "http://localhost:8000"
RESULTS = []

def record(category: str, feature: str, passed: bool, details: str = "", latency_ms: float = 0.0):
    RESULTS.append({
        "category": category,
        "feature": feature,
        "passed": passed,
        "details": details,
        "latency_ms": round(latency_ms, 2),
    })
    status_icon = "✓ PASS" if passed else "✗ FAIL"
    print(f"[{status_icon}] {category:25} | {feature:32} | {details}")


def run_checks():
    print("=" * 80)
    print("  NEXUS AI VOICE ASSISTANT — EXHAUSTIVE FEATURE VERIFICATION MATRIX")
    print("=" * 80)
    print()

    client = httpx.Client(base_url=BASE_URL, timeout=15.0)

    # ----------------------------------------------------------------------- #
    # Category 1: System Health & Infrastructure
    # ----------------------------------------------------------------------- #
    print("--- [1] System Health & Infrastructure ---")
    t0 = time.perf_counter()
    res = client.get("/api/health")
    lat = (time.perf_counter() - t0) * 1000
    h_data = res.json() if res.status_code == 200 else {}
    record("Infrastructure", "Health Probe (/api/health)", res.status_code == 200 and h_data.get("status") == "healthy", f"Status: {h_data.get('status')}, Model: {h_data.get('model')}", lat)

    # SQLite WAL mode
    with get_db_connection() as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        wal_mode = row[0].lower() if row else "unknown"
    record("Infrastructure", "SQLite WAL Mode", wal_mode in ["wal", "memory"], f"Journal Mode: {wal_mode.upper()}")

    # LiveKit Cloud Config
    t0 = time.perf_counter()
    lk_res = client.get("/api/livekit/status").json()
    lat = (time.perf_counter() - t0) * 1000
    record("Infrastructure", "LiveKit WebRTC Status", lk_res.get("configured") is True, f"Cloud URL: {lk_res.get('url')}", lat)

    # Google OAuth Config
    t0 = time.perf_counter()
    g_res = client.get("/api/auth/google/status").json()
    lat = (time.perf_counter() - t0) * 1000
    record("Infrastructure", "Google OAuth Status", g_res.get("oauth_configured") is True, f"Configured: {g_res.get('oauth_configured')}", lat)

    print()

    # ----------------------------------------------------------------------- #
    # Category 2: Authentication & User Accounts
    # ----------------------------------------------------------------------- #
    print("--- [2] Authentication & Security ---")
    test_username = f"testuser_{uuid.uuid4().hex[:6]}"
    test_password = "SecurePassword123!"
    test_email = f"{test_username}@example.com"

    # Signup
    t0 = time.perf_counter()
    signup_res = client.post("/api/auth/signup", json={"username": test_username, "password": test_password, "email": test_email})
    lat = (time.perf_counter() - t0) * 1000
    signup_ok = signup_res.status_code == 200 and signup_res.json().get("success") is True
    record("Authentication", "User Registration (Signup)", signup_ok, f"User: {test_username}", lat)

    # Login
    t0 = time.perf_counter()
    login_res = client.post("/api/auth/login", json={"username": test_username, "password": test_password})
    lat = (time.perf_counter() - t0) * 1000
    token = login_res.json().get("token") if login_res.status_code == 200 else None
    login_ok = bool(token)
    record("Authentication", "User Authentication (Login)", login_ok, f"JWT Token generated", lat)

    # Auth Me
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    t0 = time.perf_counter()
    me_res = client.get("/api/auth/me", headers=headers)
    lat = (time.perf_counter() - t0) * 1000
    me_ok = me_res.status_code == 200 and me_res.json().get("authenticated") is True
    record("Authentication", "Session Verification (/me)", me_ok, f"Authenticated: {me_ok}", lat)

    # Bad login rejection
    bad_login = client.post("/api/auth/login", json={"username": test_username, "password": "WrongPassword!"})
    record("Authentication", "Bad Password Rejection", bad_login.status_code == 401, "Returned 401 Unauthorized")

    print()

    # ----------------------------------------------------------------------- #
    # Category 3: Conversational Intelligence & History
    # ----------------------------------------------------------------------- #
    print("--- [3] Conversational Intelligence & History ---")
    sess_id = f"test-sess-{uuid.uuid4().hex[:6]}"

    # Turn 1
    t0 = time.perf_counter()
    chat1 = client.post("/api/chat", json={"message": "Hello, my name is Alex.", "session_id": sess_id}, headers=headers).json()
    lat = (time.perf_counter() - t0) * 1000
    turn1_ok = bool(chat1.get("spoken_reply"))
    record("Conversation", "Single-Turn Chat Dispatch", turn1_ok, f"Reply: '{chat1.get('spoken_reply')[:40]}...'", lat)

    # Turn 2 (Context recall)
    t0 = time.perf_counter()
    chat2 = client.post("/api/chat", json={"message": "What is my name?", "session_id": sess_id}, headers=headers).json()
    lat = (time.perf_counter() - t0) * 1000
    turn2_ok = "alex" in chat2.get("spoken_reply", "").lower()
    record("Conversation", "Multi-Turn Context Recall", turn2_ok, f"Recognized name in turn 2", lat)

    # History retrieval
    t0 = time.perf_counter()
    hist_res = client.get(f"/api/history/{sess_id}", headers=headers).json()
    lat = (time.perf_counter() - t0) * 1000
    turns_count = len(hist_res.get("turns", []))
    record("Conversation", "Chat History Persistence", turns_count >= 2, f"Persisted {turns_count} turns in SQLite", lat)

    # Session deletion
    t0 = time.perf_counter()
    del_res = client.delete(f"/api/sessions/{sess_id}", headers=headers).json()
    lat = (time.perf_counter() - t0) * 1000
    record("Conversation", "Session Management & Deletion", del_res.get("success") is True, "Clean session removal", lat)

    print()

    # ----------------------------------------------------------------------- #
    # Category 4: Core Agent Tools (All 7 Tools)
    # ----------------------------------------------------------------------- #
    print("--- [4] Core Tools Execution ---")

    # Tool 1: Calculator
    t0 = time.perf_counter()
    calc_res = TOOLS_REGISTRY["calculator"]("450 * 12 + 18% of 5000")
    lat = (time.perf_counter() - t0) * 1000
    calc_ok = calc_res.get("success") is True and calc_res.get("result") == 6300.0
    record("Tools", "Calculator (Compound % Math)", calc_ok, f"Result: {calc_res.get('result')}", lat)

    # Tool 2: Current Time
    t0 = time.perf_counter()
    time_res = TOOLS_REGISTRY["get_current_time"](timezone_str="Asia/Kolkata")
    lat = (time.perf_counter() - t0) * 1000
    time_ok = time_res.get("success") is True and "Asia/Kolkata" in time_res.get("timezone", "")
    record("Tools", "Clock Engine (Timezone Aware)", time_ok, f"Spoken: {time_res.get('spoken')}", lat)

    # Tool 3: App Launcher (YouTube)
    t0 = time.perf_counter()
    app_res = TOOLS_REGISTRY["open_app"]("youtube", query="lofi hip hop")
    lat = (time.perf_counter() - t0) * 1000
    app_ok = app_res.get("success") is True and "youtube.com" in app_res.get("url", "")
    record("Tools", "App Launcher (YouTube New Tab)", app_ok, f"URL: {app_res.get('url')}", lat)

    # Tool 4: WhatsApp Messenger
    t0 = time.perf_counter()
    wa_res = TOOLS_REGISTRY["send_whatsapp_message"](contact_name="Rahul", message="Hey Rahul, let's connect tomorrow!")
    lat = (time.perf_counter() - t0) * 1000
    wa_ok = wa_res.get("success") is True and ("whatsapp.com" in wa_res.get("url", ""))
    record("Tools", "WhatsApp Direct Web Messaging", wa_ok, f"Click-to-chat URL: {wa_res.get('url')}", lat)

    # Tool 5: Python Code Runner
    t0 = time.perf_counter()
    py_res = TOOLS_REGISTRY["run_python_code"]("print([x**2 for x in range(5)])")
    lat = (time.perf_counter() - t0) * 1000
    py_ok = py_res.get("success") is True and "[0, 1, 4, 9, 16]" in str(py_res.get("output"))
    record("Tools", "Python Code Execution Sandbox", py_ok, f"Output: {py_res.get('output').strip()}", lat)

    # Tool 6: Web Search (DuckDuckGo)
    t0 = time.perf_counter()
    search_res = TOOLS_REGISTRY["web_search"]("weather in New Delhi")
    lat = (time.perf_counter() - t0) * 1000
    search_ok = search_res.get("success") is True and (bool(search_res.get("results")) or bool(search_res.get("spoken")))
    record("Tools", "Live Web Search (DDG)", search_ok, f"Found {search_res.get('count', len(search_res.get('results', [])))} results", lat)

    # Tool 7: Email Sending Engine & AI Composer
    t0 = time.perf_counter()
    from agent.tools.email import _compose_email
    comp = _compose_email("Meeting rescheduled to Friday at 4 PM", "Amit")
    lat = (time.perf_counter() - t0) * 1000
    comp_ok = bool(comp.get("subject")) and "Amit" in comp.get("body", "")
    record("Tools", "AI Email Composer", comp_ok, f"Subject: '{comp.get('subject')}'", lat)

    print()

    # ----------------------------------------------------------------------- #
    # Category 5: Safety & Human Confirmation Gating
    # ----------------------------------------------------------------------- #
    print("--- [5] Safety & Confirmation Gating ---")
    write_gated = all(requires_confirmation(t) for t in ["send_email", "create_event", "delete_task"])
    read_safe = all(not requires_confirmation(t) for t in ["web_search", "calculator", "get_current_time", "open_app"])
    record("Safety", "Write Action Protection Gating", write_gated and read_safe, "100% write-action protection (100% precision)")

    confirms = ["yes", "yes please", "sure go ahead", "confirm that", "yep", "do it"]
    rejects = ["no", "cancel", "don't do that", "stop", "abort", "nope"]
    parser_ok = all(is_confirmed(c) is True for c in confirms) and all(is_confirmed(r) is False for r in rejects)
    record("Safety", "Confirmation Response Parser", parser_ok, "Natural language confirmation/rejection detection")

    print()

    # ----------------------------------------------------------------------- #
    # Category 6: Spoken Output & Speech Formatting
    # ----------------------------------------------------------------------- #
    print("--- [6] Voice Formatting & Clean Spoken Text ---")
    raw_markdown = "### Current Status\n* **Task 1**: Complete `code`\n* Check [here](http://example.com)\n"
    clean_speech = clean_spoken_text(raw_markdown)
    has_markdown = any(sym in clean_speech for sym in ["###", "**", "`", "http://", "* "])
    record("Voice Engine", "Clean Spoken Text Formatter", not has_markdown and len(clean_speech) > 0, "Zero unescaped markdown in TTS stream")

    print()

    # ----------------------------------------------------------------------- #
    # Category 7: LiveKit WebRTC & Google OAuth 2.0
    # ----------------------------------------------------------------------- #
    print("--- [7] LiveKit WebRTC & Google OAuth 2.0 ---")
    t0 = time.perf_counter()
    lk_tok = client.get("/api/livekit/token", headers=headers).json()
    lat = (time.perf_counter() - t0) * 1000
    record("Cloud Voice", "LiveKit WebRTC Token Minting", lk_tok.get("success") is True and bool(lk_tok.get("token")), f"Identity: {lk_tok.get('identity')}", lat)

    t0 = time.perf_counter()
    g_url_res = client.get("/api/auth/google/url", headers=headers).json()
    lat = (time.perf_counter() - t0) * 1000
    record("Google OAuth", "OAuth Consent URL Generation", g_url_res.get("configured") is True and "accounts.google.com" in g_url_res.get("url", ""), f"Redirect: {g_url_res.get('redirect_uri')}", lat)

    print()
    print("=" * 80)
    total_tests = len(RESULTS)
    total_passed = sum(1 for r in RESULTS if r["passed"])
    pass_pct = round((total_passed / total_tests) * 100, 1)
    print(f"  TOTAL FEATURES TESTED: {total_tests} | PASSED: {total_passed} | FAILED: {total_tests - total_passed} | SCORE: {pass_pct}%")
    print("=" * 80)

    return total_passed == total_tests


if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
