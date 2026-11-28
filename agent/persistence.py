"""Persistence and State Management Engine for Nexus AI Assistant.

Coordinates:
1. LangGraph Thread Checkpointing:
   - SQLite checkpointer (db/checkpoints.sqlite) with WAL mode concurrency
   - Thread state inspection, task resumption, and interrupt query API
   - Survives server reboots, crashes, and process reloads
2. Multi-Store State Synchronization:
   - Chat history, sessions, tasks, and memory facts in SQLite
   - Local trace spans and execution metrics
   - Session data export and comprehensive persistence health validation
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from db.models import (
    db_get_session_turns,
    db_list_chat_sessions,
    db_list_facts,
    db_list_tasks,
    db_list_traces,
    get_db_connection,
)

logger = logging.getLogger("nexus.persistence")

CHECKPOINTS_DB_PATH = os.environ.get(
    "NEXUS_TEST_CHECKPOINTS_DB_PATH",
    os.environ.get(
        "CHECKPOINTS_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "checkpoints.sqlite"),
    ),
)

_GLOBAL_CHECKPOINTER: Optional[BaseCheckpointSaver] = None
_GLOBAL_CHECKPOINTER_PATH: Optional[str] = None
_GLOBAL_CHECKPOINTER_CONN: Optional[sqlite3.Connection] = None


def _resolve_checkpoints_db_path(explicit_path: Optional[str] = None) -> str:
    """Resolve the active LangGraph checkpoints SQLite path honoring test/env overrides."""
    if explicit_path:
        return explicit_path
    return (
        os.environ.get("NEXUS_TEST_CHECKPOINTS_DB_PATH")
        or os.environ.get("CHECKPOINTS_DB_PATH")
        or CHECKPOINTS_DB_PATH
    )


def reset_checkpointer() -> None:
    """Close and reset any cached singleton checkpointer connection."""
    global _GLOBAL_CHECKPOINTER, _GLOBAL_CHECKPOINTER_PATH, _GLOBAL_CHECKPOINTER_CONN
    if _GLOBAL_CHECKPOINTER_CONN is not None:
        try:
            _GLOBAL_CHECKPOINTER_CONN.close()
        except Exception:
            pass
    _GLOBAL_CHECKPOINTER = None
    _GLOBAL_CHECKPOINTER_PATH = None
    _GLOBAL_CHECKPOINTER_CONN = None


def get_checkpointer(db_path: Optional[str] = None) -> BaseCheckpointSaver:
    """Get or create singleton persistent SQLite checkpointer in WAL mode."""
    global _GLOBAL_CHECKPOINTER, _GLOBAL_CHECKPOINTER_PATH, _GLOBAL_CHECKPOINTER_CONN
    target_path = _resolve_checkpoints_db_path(db_path)
    if (
        _GLOBAL_CHECKPOINTER is not None
        and db_path is None
        and _GLOBAL_CHECKPOINTER_PATH == target_path
    ):
        return _GLOBAL_CHECKPOINTER

    try:
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        conn = sqlite3.connect(target_path, check_same_thread=False)
        # Enable WAL mode on checkpoint database
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        saver = SqliteSaver(conn)
        saver.setup()
        if db_path is None:
            reset_checkpointer()
            _GLOBAL_CHECKPOINTER = saver
            _GLOBAL_CHECKPOINTER_PATH = target_path
            _GLOBAL_CHECKPOINTER_CONN = conn
        return saver
    except Exception as exc:
        logger.warning(f"Failed to initialize SqliteSaver at {target_path} ({exc}); falling back to InMemorySaver")
        return InMemorySaver()


def get_checkpoint_state(thread_id: str, graph_instance: Any = None) -> Dict[str, Any]:
    """Inspect state of a LangGraph thread checkpoint.

    Returns:
        Dict with message count, next tasks, pending interrupts, and values.
    """
    if graph_instance is None:
        from agent.lc_agent import graph
        graph_instance = graph

    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        state = graph_instance.get_state(cfg)
        interrupts = []
        if state and state.tasks:
            for t in state.tasks:
                if t.interrupts:
                    for intr in t.interrupts:
                        interrupts.append(intr.value if hasattr(intr, "value") else str(intr))

        msg_count = len(state.values.get("messages", [])) if state and state.values else 0
        return {
            "thread_id": thread_id,
            "exists": bool(state and state.values),
            "message_count": msg_count,
            "next": list(state.next) if state and state.next else [],
            "has_interrupt": len(interrupts) > 0,
            "interrupts": interrupts,
            "status": "pending_approval" if interrupts else ("active" if state and state.next else "idle"),
        }
    except Exception as exc:
        logger.error(f"Error fetching checkpoint state for {thread_id}: {exc}")
        return {
            "thread_id": thread_id,
            "exists": False,
            "error": str(exc),
            "has_interrupt": False,
            "status": "error",
        }


def list_saved_threads(limit: int = 50) -> List[Dict[str, Any]]:
    """Query thread IDs stored in the SQLite checkpointer database."""
    target_path = _resolve_checkpoints_db_path()
    if not os.path.exists(target_path):
        return []

    conn = None
    try:
        conn = sqlite3.connect(target_path, check_same_thread=False)
        cur = conn.cursor()
        # Query distinct thread IDs from checkpoints table
        cur.execute(
            "SELECT thread_id, checkpoint_id, checkpoint_ns FROM checkpoints "
            "GROUP BY thread_id ORDER BY rowid DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "thread_id": r[0],
                "latest_checkpoint_id": r[1],
                "namespace": r[2],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug(f"Could not query checkpoints table directly: {exc}")
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def delete_thread_checkpoint(thread_id: str) -> bool:
    """Delete checkpoint records for a specific thread."""
    target_path = _resolve_checkpoints_db_path()
    if not os.path.exists(target_path):
        return False

    conn = None
    try:
        conn = sqlite3.connect(target_path, check_same_thread=False)
        conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = ?", (thread_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.error(f"Error deleting checkpoint for {thread_id}: {exc}")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def export_session_bundle(session_id: str, user_id: str = "guest") -> Dict[str, Any]:
    """Export complete persistent session state (chat turns, traces, checkpoint status)."""
    turns = db_get_session_turns(user_id=user_id, session_id=session_id)
    traces = db_list_traces(limit=25, session_id=session_id)
    ckpt = get_checkpoint_state(thread_id=session_id)

    return {
        "session_id": session_id,
        "user_id": user_id,
        "turns": turns,
        "traces": traces,
        "checkpoint": ckpt,
        "turn_count": len(turns),
        "trace_count": len(traces),
    }


def health_check_persistence() -> Dict[str, Any]:
    """Validate persistence layers: SQLite WAL status, checkpointer connectivity, and record counts."""
    db_ok = False
    wal_mode = False
    counts = {}

    try:
        with get_db_connection() as conn:
            mode_row = conn.execute("PRAGMA journal_mode;").fetchone()
            wal_mode = bool(mode_row and str(mode_row[0]).lower() == "wal")
            for table in ["tasks", "memory_facts", "chat_history", "execution_traces", "users"]:
                cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
        db_ok = True
    except Exception as e:
        logger.error(f"Database health check error: {e}")

    ckpt_ok = False
    try:
        saver = get_checkpointer()
        ckpt_ok = saver is not None
    except Exception as e:
        logger.error(f"Checkpointer health check error: {e}")

    return {
        "database_connected": db_ok,
        "wal_mode_active": wal_mode,
        "checkpointer_connected": ckpt_ok,
        "record_counts": counts,
        "status": "healthy" if db_ok and ckpt_ok else "degraded",
    }
