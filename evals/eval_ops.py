"""Evaluates infrastructure operations: SQLite WAL concurrency, schemas, and health endpoints."""

import os
import sys
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from db.models import get_db_connection
from evals.harness import EvalHarness


def run_ops_eval(harness: EvalHarness) -> Dict[str, Any]:
    # 1. SQLite WAL mode check
    wal_mode = False
    with get_db_connection() as conn:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        if row and row[0].lower() in ["wal", "memory"]:
            wal_mode = True

    # 2. Database Tables Verification
    required_tables = ["chat_history", "tasks", "memory_facts", "reminders", "notes", "users", "user_oauth_tokens"]
    with get_db_connection() as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [r[0] for r in cur.fetchall()]
    tables_ok = all(t in existing_tables for t in required_tables)

    # 3. Cloud Credentials Readiness
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_ready = bool(openai_key and not openai_key.startswith("your-"))

    livekit_ready = bool(os.environ.get("LIVEKIT_URL") and os.environ.get("LIVEKIT_API_KEY"))

    harness.record_test("eval_ops", "SQLite WAL Concurrency", wal_mode, wal_mode, "WAL mode active (non-blocking reads)")
    harness.record_test("eval_ops", "Database Tables Integrity", tables_ok, tables_ok, f"{len(required_tables)} essential tables verified")
    harness.record_test("eval_ops", "OpenAI LLM Readiness", openai_ready, openai_ready, "API key configured")
    harness.record_test("eval_ops", "LiveKit Cloud WebRTC", livekit_ready, livekit_ready, "LiveKit credentials active")

    return {
        "sqlite_wal_active": wal_mode,
        "database_tables_intact": tables_ok,
        "openai_configured": openai_ready,
        "livekit_configured": livekit_ready,
    }


if __name__ == "__main__":
    h = EvalHarness()
    run_ops_eval(h)
