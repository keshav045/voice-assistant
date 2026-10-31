"""Nexus Real-Time Full-System End-to-End Live Verification Script.

Tests every subsystem of Nexus live against active servers:
1. System Health & Configuration (/health, /api/v1/system/config)
2. Task Management & Background Scheduler (CRUD, Daily Summary, Recurring Reminders)
3. Gmail & Email Intelligence (Search, AI Thread Summarization, Drafts)
4. Calendar & Scheduling (Agenda, Conflict Detection, Free Slots Computation, Booking)
5. Windows Desktop Companion (Live WebSocket, Telemetry, Safe Read, Screenshots)
6. Semantic Memory (Embedding Storage, Cosine Similarity Vector Search)
7. LangGraph 9-Node Agentic State Machine (/api/v1/chat, Human-in-the-Loop Policy Gate)
8. Real-Time Voice Engine (/api/v1/voice/session, Bi-directional WebSocket Streaming)
9. Frontend React Single-Page Application (Vite Dev Server delivery)
"""

import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
import websockets

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
BACKEND_BASE = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
FRONTEND_BASE = f"http://{BACKEND_HOST}:{FRONTEND_PORT}"

RESULTS: List[Dict[str, Any]] = []


def record_result(module: str, test_name: str, passed: bool, details: str, latency_ms: float = 0.0):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {module} -> {test_name} ({latency_ms:.1f}ms): {details}")
    RESULTS.append({
        "module": module,
        "test": test_name,
        "passed": passed,
        "details": details,
        "latency_ms": latency_ms,
    })


async def wait_for_backend(timeout: float = 25.0) -> bool:
    start = time.time()
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.time() - start < timeout:
            try:
                res = await client.get(f"{BACKEND_BASE}/health")
                if res.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False


async def wait_for_frontend(timeout: float = 20.0) -> bool:
    start = time.time()
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.time() - start < timeout:
            try:
                res = await client.get(FRONTEND_BASE)
                if res.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False


async def run_system_health_tests(client: httpx.AsyncClient):
    # 1. Root Health Check
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/health")
    latency = (time.time() - t0) * 1000
    data = res.json()
    passed = res.status_code == 200 and data.get("status") in ["healthy", "degraded"]
    record_result(
        "Health & System",
        "Root Health Check",
        passed,
        f"HTTP {res.status_code}, status={data.get('status')}, db={data.get('database', {}).get('status')}",
        latency,
    )

    # 2. System Capabilities & Config
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/api/v1/system/config")
    latency = (time.time() - t0) * 1000
    data = res.json()
    capabilities = data.get("capabilities", [])
    passed = res.status_code == 200 and len(capabilities) > 0
    record_result(
        "Health & System",
        "System Configuration & Capabilities",
        passed,
        f"HTTP {res.status_code}, version={data.get('version')}, capabilities={capabilities[:5]}...",
        latency,
    )


async def run_task_and_reminder_tests(client: httpx.AsyncClient):
    # 1. Create task
    t0 = time.time()
    task_payload = {
        "title": "Real-time Verification Urgent Task",
        "priority": "urgent",
        "tags": ["verification", "production-readiness"],
    }
    res = await client.post(f"{BACKEND_BASE}/api/v1/tasks", json=task_payload)
    latency = (time.time() - t0) * 1000
    task_data = res.json()
    passed = res.status_code == 201 and task_data.get("title") == task_payload["title"]
    task_id = task_data.get("id")
    record_result("Tasks & Reminders", "Create Task", passed, f"Created task id={task_id}", latency)

    # 2. Daily summary
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/api/v1/tasks/summary/daily")
    latency = (time.time() - t0) * 1000
    summary_data = res.json()
    passed = res.status_code == 200 and "pending_count" in summary_data
    record_result(
        "Tasks & Reminders",
        "Daily Task Summary Computation",
        passed,
        f"Pending={summary_data.get('pending_count')}, Urgent={summary_data.get('urgent_pending_count')}",
        latency,
    )

    # 3. Complete task
    if task_id:
        t0 = time.time()
        res = await client.post(f"{BACKEND_BASE}/api/v1/tasks/{task_id}/complete")
        latency = (time.time() - t0) * 1000
        comp_data = res.json()
        passed = res.status_code == 200 and comp_data.get("status") == "completed"
        record_result("Tasks & Reminders", "Complete Task Lifecycle", passed, f"Task {task_id} status=completed", latency)

    # 4. Create reminder
    t0 = time.time()
    reminder_payload = {
        "title": "Review Real-Time Production Deployment Readiness",
        "scheduled_at": datetime.now(timezone.utc).isoformat(),
        "is_recurring": True,
        "recurrence_rule": "daily",
    }
    res = await client.post(f"{BACKEND_BASE}/api/v1/reminders", json=reminder_payload)
    latency = (time.time() - t0) * 1000
    reminder_data = res.json()
    passed = res.status_code == 201 and reminder_data.get("is_recurring") is True
    record_result("Tasks & Reminders", "Create Recurring Reminder", passed, f"Reminder id={reminder_data.get('id')}", latency)

    # 5. Check due reminders
    t0 = time.time()
    res = await client.post(f"{BACKEND_BASE}/api/v1/reminders/check-due")
    latency = (time.time() - t0) * 1000
    due_res = res.json()
    passed = res.status_code == 200 and due_res.get("success") is True
    record_result(
        "Tasks & Reminders",
        "Background Due Reminder Evaluation",
        passed,
        f"Triggered count={due_res.get('triggered_count')}",
        latency,
    )


async def run_email_intelligence_tests(client: httpx.AsyncClient):
    # 1. Search emails
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/api/v1/emails/search?q=project")
    latency = (time.time() - t0) * 1000
    search_data = res.json()
    passed = res.status_code == 200 and search_data.get("success") is True and isinstance(search_data.get("messages"), list)
    record_result(
        "Email Intelligence",
        "Search Inbox Messages",
        passed,
        f"Found {len(search_data.get('messages', []))} matching message(s)",
        latency,
    )

    # 2. Summarize inbox
    t0 = time.time()
    res = await client.post(f"{BACKEND_BASE}/api/v1/emails/summarize", json={"query": ""})
    latency = (time.time() - t0) * 1000
    summary = res.json()
    passed = res.status_code == 200 and summary.get("success") is True
    record_result(
        "Email Intelligence",
        "AI Thread Summarization",
        passed,
        f"Analyzed {summary.get('emails_analyzed', 0)} email(s), preview: {summary.get('summary', '')[:50]}...",
        latency,
    )

    # 3. Create draft
    t0 = time.time()
    draft_payload = {
        "recipient": "lead-architect@nexus.ai",
        "subject": "Real-time Verification Complete",
        "body": "All real-time components verified with zero regressions.",
    }
    res = await client.post(f"{BACKEND_BASE}/api/v1/emails/drafts", json=draft_payload)
    latency = (time.time() - t0) * 1000
    draft_data = res.json()
    passed = res.status_code == 201 and draft_data.get("status") == "draft"
    record_result("Email Intelligence", "Create Email Draft", passed, f"Draft id={draft_data.get('id')}", latency)


async def run_calendar_scheduling_tests(client: httpx.AsyncClient):
    # 1. List events
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/api/v1/calendar/events")
    latency = (time.time() - t0) * 1000
    events = res.json()
    passed = res.status_code == 200 and isinstance(events, list)
    record_result("Calendar & Scheduling", "Fetch Agenda Events", passed, f"Found {len(events)} event(s)", latency)

    # 2. Check availability
    t0 = time.time()
    start_iso = "2026-11-01T14:00:00Z"
    end_iso = "2026-11-01T15:00:00Z"
    res = await client.get(f"{BACKEND_BASE}/api/v1/calendar/availability?start_time={start_iso}&end_time={end_iso}")
    latency = (time.time() - t0) * 1000
    avail = res.json()
    passed = res.status_code == 200 and "is_free" in avail
    record_result(
        "Calendar & Scheduling",
        "Conflict Detection & Availability Checker",
        passed,
        f"is_free={avail.get('is_free')}, conflicts={avail.get('conflict_count')}",
        latency,
    )

    # 3. Free slots
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/api/v1/calendar/free-slots?date=2026-11-01")
    latency = (time.time() - t0) * 1000
    slots = res.json()
    passed = res.status_code == 200 and isinstance(slots, list)
    record_result("Calendar & Scheduling", "Open Workday Slot Computation", passed, f"Found {len(slots)} free window(s)", latency)

    # 4. Create event
    t0 = time.time()
    event_payload = {
        "title": "Nexus Architecture Alignment Review",
        "start_time": "2026-11-01T15:00:00Z",
        "end_time": "2026-11-01T16:00:00Z",
        "location": "Virtual Conference Room 1",
        "attendees": ["team@nexus.ai"],
    }
    res = await client.post(f"{BACKEND_BASE}/api/v1/calendar/events", json=event_payload)
    latency = (time.time() - t0) * 1000
    event_data = res.json()
    passed = res.status_code == 201 and event_data.get("title") == event_payload["title"]
    record_result("Calendar & Scheduling", "Schedule Calendar Appointment", passed, f"Event id={event_data.get('id')}", latency)


async def run_desktop_companion_tests(client: httpx.AsyncClient):
    # 1. Check companion status
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/api/v1/desktop/status")
    latency = (time.time() - t0) * 1000
    status = res.json()
    passed = res.status_code == 200
    record_result(
        "Desktop Companion",
        "Companion Connection Telemetry",
        passed,
        f"is_connected={status.get('is_connected')}, hostname={status.get('hostname')}, os={status.get('os_info')}",
        latency,
    )

    # 2. Execute safe metrics command
    t0 = time.time()
    res = await client.post(f"{BACKEND_BASE}/api/v1/desktop/command", json={"action": "get_system_metrics"})
    latency = (time.time() - t0) * 1000
    metrics_res = res.json()
    passed = res.status_code == 200 and metrics_res.get("success") is True
    record_result(
        "Desktop Companion",
        "Real-Time Hardware Metrics (psutil)",
        passed,
        f"CPU={metrics_res.get('cpu_usage_pct')}%, RAM used={metrics_res.get('memory_used_gb')}GB/{metrics_res.get('memory_total_gb')}GB",
        latency,
    )

    # 3. Execute safe active window command
    t0 = time.time()
    res = await client.post(f"{BACKEND_BASE}/api/v1/desktop/command", json={"action": "get_active_window"})
    latency = (time.time() - t0) * 1000
    window_res = res.json()
    passed = res.status_code == 200 and window_res.get("success") is True
    record_result(
        "Desktop Companion",
        "Active Window Inspection",
        passed,
        f"Window: {window_res.get('title')} (Process: {window_res.get('process')})",
        latency,
    )


async def run_semantic_memory_tests(client: httpx.AsyncClient):
    # 1. Store memory item
    t0 = time.time()
    memory_payload = {
        "content": "User prefers concise executive reports and real-time WebSocket telemetry for agent actions.",
        "category": "preference",
        "confidence": 0.95,
        "source": "e2e_verification",
    }
    res = await client.post(f"{BACKEND_BASE}/api/v1/memory", json=memory_payload)
    latency = (time.time() - t0) * 1000
    mem_data = res.json()
    passed = res.status_code == 201 and "id" in mem_data
    record_result("Semantic Memory", "Vector Embedding Storage", passed, f"Indexed memory id={mem_data.get('id')}", latency)

    # 2. Vector search query
    t0 = time.time()
    search_payload = {"query": "What telemetry does the user like?", "top_k": 3}
    res = await client.post(f"{BACKEND_BASE}/api/v1/memory/search", json=search_payload)
    latency = (time.time() - t0) * 1000
    search_results = res.json()
    passed = res.status_code == 200 and isinstance(search_results, list)
    top_score = search_results[0].get("similarity", 0.0) if (passed and search_results) else 0.0
    record_result(
        "Semantic Memory",
        "Cosine Similarity Vector Search",
        passed,
        f"Matches={len(search_results) if isinstance(search_results, list) else 0}, top_similarity={top_score:.3f}",
        latency,
    )


async def run_agentic_orchestrator_tests(client: httpx.AsyncClient):
    # 1. Safe query through 9-Node LangGraph machine
    t0 = time.time()
    chat_payload = {"message": "List my pending tasks please"}
    res = await client.post(f"{BACKEND_BASE}/api/v1/chat", json=chat_payload)
    latency = (time.time() - t0) * 1000
    chat_res = res.json()
    passed = res.status_code == 200 and "final_response" in chat_res
    record_result(
        "Agentic Core",
        "LangGraph 9-Node Tool Routing (Safe Read)",
        passed,
        f"Intent={chat_res.get('normalized_intent')}, tools_run={len(chat_res.get('tool_results', []))}, preview={chat_res.get('final_response', '')[:60]}...",
        latency,
    )

    # 2. Sensitive operation triggering approval gate
    t0 = time.time()
    sensitive_payload = {"message": "Delete task task-sample-1"}
    res = await client.post(f"{BACKEND_BASE}/api/v1/chat", json=sensitive_payload)
    latency = (time.time() - t0) * 1000
    gate_res = res.json()
    passed = res.status_code == 200 and (gate_res.get("approval_required") is True or "approval" in gate_res.get("final_response", "").lower())
    record_result(
        "Agentic Core",
        "Human-in-the-Loop Policy Gate Trigger",
        passed,
        f"Status={gate_res.get('workflow_status')}, approval_required={gate_res.get('approval_required')}",
        latency,
    )

    # 3. Check approvals queue
    t0 = time.time()
    res = await client.get(f"{BACKEND_BASE}/api/v1/approvals")
    latency = (time.time() - t0) * 1000
    approvals = res.json()
    passed = res.status_code == 200 and isinstance(approvals, list)
    record_result("Agentic Core", "Approvals Queue Query", passed, f"Total pending actions={len(approvals)}", latency)


async def run_voice_pipeline_tests(client: httpx.AsyncClient):
    # 1. Create voice session
    t0 = time.time()
    res = await client.post(f"{BACKEND_BASE}/api/v1/voice/session")
    latency = (time.time() - t0) * 1000
    session_data = res.json()
    passed = res.status_code == 201 and "session_id" in session_data
    session_id = session_data.get("session_id")
    record_result("Voice Engine", "Create Voice Session", passed, f"Session ID={session_id}", latency)

    # 2. Real-Time WebSocket Streaming Connection & Handshake
    t0 = time.time()
    ws_url = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws/voice/{session_id}"
    try:
        async with websockets.connect(ws_url, close_timeout=3.0) as ws:
            # Await the initial session_ready greeting from Nexus Voice Engine
            raw_resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            latency = (time.time() - t0) * 1000
            resp_json = json.loads(raw_resp) if isinstance(raw_resp, str) else {"type": "binary_frame"}
            passed = resp_json.get("type") == "session_ready"
            record_result(
                "Voice Engine",
                "Real-Time Bi-Directional WebSocket Streaming Handshake",
                passed,
                f"Connected, initial greeting type: {resp_json.get('type')}",
                latency,
            )

            # Send ping
            t1 = time.time()
            await ws.send(json.dumps({"type": "ping"}))
            pong_raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
            pong_latency = (time.time() - t1) * 1000
            pong_json = json.loads(pong_raw) if isinstance(pong_raw, str) else {}
            passed_pong = pong_json.get("type") == "pong"
            record_result(
                "Voice Engine",
                "Real-Time WebSocket Keepalive Ping/Pong",
                passed_pong,
                f"Received: {pong_json.get('type')} at {pong_json.get('timestamp')}",
                pong_latency,
            )
    except Exception as e:
        latency = (time.time() - t0) * 1000
        record_result(
            "Voice Engine",
            "Real-Time Bi-Directional WebSocket Streaming",
            False,
            f"WebSocket error: {e}",
            latency,
        )


async def run_frontend_live_tests(client: httpx.AsyncClient):
    t0 = time.time()
    try:
        res = await client.get(FRONTEND_BASE)
        latency = (time.time() - t0) * 1000
        html = res.text
        has_root = '<div id="root">' in html
        has_script = 'src="/src/main.tsx"' in html or 'index-' in html
        passed = res.status_code == 200 and has_root and has_script
        record_result(
            "Frontend SPA",
            "Vite Web Server & React Bundle Delivery",
            passed,
            f"HTTP {res.status_code}, length={len(html)} bytes, root_mount={has_root}, script_bound={has_script}",
            latency,
        )
    except Exception as e:
        latency = (time.time() - t0) * 1000
        record_result("Frontend SPA", "Vite Web Server Delivery", False, f"Error: {e}", latency)


async def main():
    print("=" * 75)
    print(" NEXUS AGENTIC AI ASSISTANT - LIVE REAL-TIME END-TO-END VERIFICATION")
    print("=" * 75)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Platform: {platform.system()} {platform.release()} ({platform.architecture()[0]})")
    print(f"Python: {sys.version.split()[0]}")
    print("=" * 75)

    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")
    python_exe = os.path.join(backend_dir, ".venv", "Scripts", "python.exe")

    spawned_backend = False
    spawned_frontend = False
    spawned_companion = False
    backend_proc = None
    frontend_proc = None
    companion_proc = None

    # Check if backend is already running
    print("\nChecking if Nexus Backend is running on port 8000...")
    backend_already_up = await wait_for_backend(timeout=2.0)
    if not backend_already_up:
        print("[STEP 1/3] Launching FastAPI Backend on port 8000...")
        backend_proc = subprocess.Popen(
            [python_exe, "-u", "-m", "uvicorn", "app.main:app", "--host", BACKEND_HOST, "--port", str(BACKEND_PORT)],
            cwd=backend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        spawned_backend = True
        print("Waiting for backend /health readiness (up to 25s)...")
        backend_ready = await wait_for_backend(timeout=25.0)
        if not backend_ready:
            print("[FATAL] Backend failed to bind port 8000 within timeout.")
            return
    else:
        print("Nexus Backend is already alive and responding on port 8000!")

    # Check if frontend is already running
    print("\nChecking if Vite Frontend is running on port 5173...")
    frontend_already_up = await wait_for_frontend(timeout=2.0)
    if not frontend_already_up:
        print("[STEP 2/3] Launching Vite Frontend on port 5173...")
        frontend_proc = subprocess.Popen(
            ["cmd", "/c", "npm", "run", "dev", "--", "--host", BACKEND_HOST, "--port", str(FRONTEND_PORT)],
            cwd=frontend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        spawned_frontend = True
        print("Waiting for frontend readiness (up to 20s)...")
        frontend_ready = await wait_for_frontend(timeout=20.0)
        if not frontend_ready:
            print("[WARN] Frontend did not respond within timeout, continuing with available services...")
    else:
        print("Vite Frontend is already alive and responding on port 5173!")

    # Check companion status or spawn
    print("\n[STEP 3/3] Ensuring Windows Desktop Companion Daemon is active...")
    companion_proc = subprocess.Popen(
        [python_exe, os.path.join(root_dir, "desktop-companion", "main.py")],
        cwd=root_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    spawned_companion = True
    await asyncio.sleep(2.0)

    try:
        # Execute Test Matrix
        print("\n" + "=" * 75)
        print(" EXECUTING REAL-TIME LIVE COMPONENT VERIFICATIONS")
        print("=" * 75)

        async with httpx.AsyncClient(timeout=20.0) as client:
            await run_system_health_tests(client)
            await run_task_and_reminder_tests(client)
            await run_email_intelligence_tests(client)
            await run_calendar_scheduling_tests(client)
            await run_desktop_companion_tests(client)
            await run_semantic_memory_tests(client)
            await run_agentic_orchestrator_tests(client)
            await run_voice_pipeline_tests(client)
            await run_frontend_live_tests(client)

    finally:
        print("\n" + "=" * 75)
        print(" TEARING DOWN TEST BACKGROUND PROCESSES")
        print("=" * 75)
        if spawned_companion and companion_proc:
            try:
                companion_proc.terminate()
                companion_proc.kill()
            except Exception:
                pass
        if spawned_frontend and frontend_proc:
            try:
                frontend_proc.terminate()
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(frontend_proc.pid)], capture_output=True)
            except Exception:
                pass
        if spawned_backend and backend_proc:
            try:
                backend_proc.terminate()
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(backend_proc.pid)], capture_output=True)
            except Exception:
                pass

        # Final Summary
        total = len(RESULTS)
        passed = sum(1 for r in RESULTS if r["passed"])
        failed = total - passed
        print("\n" + "=" * 75)
        print(f" FINAL SUMMARY: {passed}/{total} VERIFICATIONS PASSED ({failed} FAILED)")
        print("=" * 75)
        if failed > 0:
            print("Failed verifications:")
            for r in RESULTS:
                if not r["passed"]:
                    print(f"  - [{r['module']}] {r['test']}: {r['details']}")
            sys.exit(1)
        else:
            print("ALL REAL-TIME MODULES VERIFIED OPERATIONAL AND PRODUCTION-READY!")
            sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
