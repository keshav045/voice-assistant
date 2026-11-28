"""Database access and models for Personal Voice Assistant."""

import sqlite3
import os
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

default_db_path = (
    "/tmp/voice_assistant.db"
    if IS_SERVERLESS
    else os.path.join(os.path.dirname(os.path.dirname(__file__)), "voice_assistant.db")
)

_INITIAL_DB_PATH = os.environ.get(
    "NEXUS_TEST_DB_PATH",
    os.environ.get("DB_PATH", os.environ.get("SQLITE_DB_PATH", default_db_path)),
)
DB_PATH = _INITIAL_DB_PATH
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def _resolve_db_path() -> str:
    """Resolve active SQLite database path while honoring test/runtime overrides."""
    if DB_PATH != _INITIAL_DB_PATH:
        return DB_PATH
    return (
        os.environ.get("NEXUS_TEST_DB_PATH")
        or os.environ.get("DB_PATH")
        or os.environ.get("SQLITE_DB_PATH")
        or DB_PATH
    )


def get_db_connection() -> sqlite3.Connection:
    """Return a production-ready connection to the SQLite database with WAL mode (or standard rollback on serverless)."""
    active_path = _resolve_db_path()
    db_dir = os.path.dirname(os.path.abspath(active_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(active_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        if not IS_SERVERLESS:
            conn.execute("PRAGMA journal_mode=WAL;")
        else:
            conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_ddl: str) -> None:
    """Safely add a column to an existing SQLite table if missing."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_ddl}")


def init_db() -> None:
    """Initialize database tables from schema.sql and run safe forward migrations."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with get_db_connection() as conn:
        conn.executescript(schema_sql)
        _ensure_column(conn, "tasks", "user_id", "TEXT NOT NULL DEFAULT 'guest'")
        _ensure_column(conn, "tasks", "priority", "TEXT NOT NULL DEFAULT 'medium'")
        _ensure_column(conn, "memory_facts", "user_id", "TEXT NOT NULL DEFAULT 'guest'")
        _ensure_column(conn, "reminders", "user_id", "TEXT NOT NULL DEFAULT 'guest'")
        _ensure_column(conn, "notes", "user_id", "TEXT NOT NULL DEFAULT 'guest'")
        _ensure_column(conn, "doc_chunks", "user_id", "TEXT NOT NULL DEFAULT 'guest'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_calendar_events_user_start ON calendar_events(user_id, start)")
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL")
        except sqlite3.IntegrityError:
            pass
        conn.commit()


# --- Task Operations ---
def _resolve_task_row(
    conn: sqlite3.Connection,
    task_id: str,
    user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a single task row by exact ID, exact title, or >=3-char title substring."""
    clean = str(task_id or "").strip()
    if not clean:
        return None
    uid_clause = " AND user_id = ?" if user_id else ""
    uid_params = (user_id,) if user_id else ()

    # 1. Exact primary ID match
    cur = conn.execute(
        f"SELECT * FROM tasks WHERE id = ?{uid_clause} LIMIT 1",
        (clean, *uid_params),
    )
    row = cur.fetchone()
    if row:
        return dict(row)

    # 2. Case-insensitive exact title match
    cur = conn.execute(
        f"SELECT * FROM tasks WHERE LOWER(title) = LOWER(?){uid_clause} ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (clean, *uid_params),
    )
    row = cur.fetchone()
    if row:
        return dict(row)

    # 3. Substring title match only for queries >= 3 chars to prevent accidental wildcard matches
    if len(clean) >= 3:
        cur = conn.execute(
            f"SELECT * FROM tasks WHERE LOWER(title) LIKE ?{uid_clause} ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (f"%{clean.lower()}%", *uid_params),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
    return None


def db_add_task(
    title: str,
    due_at: Optional[str] = None,
    priority: str = "medium",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    eff_uid = (user_id or "guest").strip() or "guest"
    eff_prio = (priority or "medium").strip().lower()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, title, priority, due_at, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (task_id, eff_uid, title, eff_prio, due_at, now),
        )
        conn.commit()
    return {
        "id": task_id,
        "user_id": eff_uid,
        "title": title,
        "priority": eff_prio,
        "due_at": due_at,
        "status": "pending",
        "created_at": now,
    }


def db_list_tasks(status: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        clauses: List[str] = []
        params: List[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = conn.execute(f"SELECT * FROM tasks{where} ORDER BY created_at DESC, rowid DESC", tuple(params))
        return [dict(row) for row in cur.fetchall()]


def db_find_task(task_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a task without mutating it (used for HITL confirmation validation)."""
    with get_db_connection() as conn:
        return _resolve_task_row(conn, task_id, user_id=user_id)


def db_complete_task(task_id: str, user_id: Optional[str] = None) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        row = _resolve_task_row(conn, task_id, user_id=user_id)
        if not row:
            return False
        cur = conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        conn.commit()
        return cur.rowcount > 0


def db_delete_task(task_id: str, user_id: Optional[str] = None) -> bool:
    with get_db_connection() as conn:
        row = _resolve_task_row(conn, task_id, user_id=user_id)
        if not row:
            return False
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (row["id"],))
        conn.commit()
        return cur.rowcount > 0


# --- Memory Operations ---
def db_add_fact(
    fact: str,
    category: str = "general",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    eff_uid = (user_id or "guest").strip() or "guest"
    clean_fact = str(fact).strip()
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM memory_facts WHERE user_id = ? AND LOWER(fact) = LOWER(?) LIMIT 1",
            (eff_uid, clean_fact),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE memory_facts SET last_used_at = ?, category = ? WHERE id = ?",
                (now, category or existing["category"], existing["id"]),
            )
            conn.commit()
            return {
                "id": existing["id"],
                "user_id": eff_uid,
                "fact": existing["fact"],
                "category": category or existing["category"],
                "created_at": existing["created_at"],
            }
        fact_id = f"fact-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO memory_facts (id, user_id, fact, category, created_at, last_used_at) VALUES (?, ?, ?, ?, ?, ?)",
            (fact_id, eff_uid, clean_fact, category, now, now),
        )
        conn.commit()
    return {"id": fact_id, "user_id": eff_uid, "fact": clean_fact, "category": category, "created_at": now}


def db_list_facts(category: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        clauses: List[str] = []
        params: List[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = conn.execute(f"SELECT * FROM memory_facts{where} ORDER BY created_at DESC, rowid DESC", tuple(params))
        return [dict(row) for row in cur.fetchall()]


def db_forget_fact(fact_query: str, user_id: Optional[str] = None) -> bool:
    clean_q = str(fact_query or "").strip()
    if not clean_q:
        return False
    with get_db_connection() as conn:
        if user_id:
            cur = conn.execute(
                "DELETE FROM memory_facts WHERE user_id = ? AND (id = ? OR LOWER(fact) LIKE ?)",
                (user_id, clean_q, f"%{clean_q.lower()}%"),
            )
        else:
            cur = conn.execute(
                "DELETE FROM memory_facts WHERE id = ? OR LOWER(fact) LIKE ?",
                (clean_q, f"%{clean_q.lower()}%"),
            )
        conn.commit()
        return cur.rowcount > 0


# --- Persistent Calendar Operations ---
def db_list_calendar_events(
    user_id: Optional[str] = None,
    calendar_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    eff_uid = (user_id or "guest").strip() or "guest"
    with get_db_connection() as conn:
        clauses = ["status != 'cancelled'", "user_id = ?"]
        params: List[Any] = [eff_uid]
        if calendar_id:
            clauses.append("calendar_id = ?")
            params.append(calendar_id)
        where = " AND ".join(clauses)
        cur = conn.execute(f"SELECT * FROM calendar_events WHERE {where} ORDER BY start ASC, rowid ASC", tuple(params))
        rows = []
        for r in cur.fetchall():
            item = dict(r)
            try:
                item["attendees"] = json.loads(item.pop("attendees_json", "[]") or "[]")
            except Exception:
                item["attendees"] = []
            rows.append(item)
        return rows


def db_add_calendar_event(
    title: str,
    start: str,
    end: str,
    attendees: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    calendar_id: str = "primary",
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    evt_id = event_id or f"evt-{uuid.uuid4().hex[:6]}"
    eff_uid = (user_id or "guest").strip() or "guest"
    now = datetime.now(timezone.utc).isoformat()
    att_list = attendees or []
    with get_db_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO calendar_events
               (id, user_id, title, start, end, attendees_json, calendar_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmed', ?)""",
            (evt_id, eff_uid, title, start, end, json.dumps(att_list), calendar_id or "primary", now),
        )
        conn.commit()
    return {
        "id": evt_id,
        "user_id": eff_uid,
        "title": title,
        "start": start,
        "end": end,
        "attendees": att_list,
        "calendar_id": calendar_id or "primary",
        "status": "confirmed",
        "created_at": now,
    }


# --- Tool Call Audit Logging ---
def db_log_tool_call(
    tool: str,
    args: Dict[str, Any],
    session_id: Optional[str] = None,
    result_size: int = 0,
    latency_ms: float = 0.0,
    error: Optional[str] = None,
) -> str:
    call_id = f"call-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    args_json = json.dumps(args)
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO tool_calls (id, session_id, tool, args_json, result_size, latency_ms, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (call_id, session_id, tool, args_json, result_size, latency_ms, error, now),
        )
        conn.commit()
    return call_id


def db_get_tool_calls(limit: int = 20) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cur = conn.execute("SELECT * FROM tool_calls ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cur.fetchall()]


# --- Paper & Chunk Operations ---
def db_save_paper(
    title: str,
    source_url: str = "",
    authors: Optional[List[str]] = None,
    file_path: str = "",
    parsed_json: str = "",
) -> str:
    paper_id = f"paper-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    authors_str = json.dumps(authors or [])
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO papers (id, source_url, title, authors, file_path, parsed_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (paper_id, source_url, title, authors_str, file_path, parsed_json, now),
        )
        conn.commit()
    return paper_id


def db_save_paper_chunks(paper_id: str, chunks: List[Dict[str, Any]]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        for ch in chunks:
            chunk_id = f"pch-{uuid.uuid4().hex[:8]}"
            conn.execute(
                "INSERT INTO paper_chunks (id, paper_id, section, chunk_index, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chunk_id, paper_id, ch.get("section", ""), ch.get("chunk_index", 0), ch.get("text", ""), now),
            )
        conn.commit()
    return len(chunks)


def db_search_paper_chunks(query: str, paper_id: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
    """Keyword / BM25-like search over paper chunks with section citations."""
    words = [w.lower() for w in query.split() if len(w) > 2]
    with get_db_connection() as conn:
        if paper_id:
            cur = conn.execute("SELECT * FROM paper_chunks WHERE paper_id = ?", (paper_id,))
        else:
            cur = conn.execute("SELECT pc.*, p.title as paper_title FROM paper_chunks pc JOIN papers p ON pc.paper_id = p.id")
        rows = [dict(r) for r in cur.fetchall()]

    if not words:
        return rows[:top_k]

    scored = []
    for r in rows:
        text_lower = r["text"].lower()
        score = sum(text_lower.count(w) for w in words)
        if score > 0:
            scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def db_save_report(paper_id: str, markdown: str, depth: str = "standard", pdf_path: str = "", verified: bool = False) -> str:
    report_id = f"rep-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO reports (id, paper_id, depth, markdown, pdf_path, verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (report_id, paper_id, depth, markdown, pdf_path, 1 if verified else 0, now),
        )
        conn.commit()
    return report_id


# --- Reminders Operations ---
def db_add_reminder(text: str, due_at: str) -> Dict[str, Any]:
    rem_id = f"rem-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO reminders (id, text, due_at, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (rem_id, text, due_at, now),
        )
        conn.commit()
    return {"id": rem_id, "text": text, "due_at": due_at, "status": "pending", "created_at": now}


def db_list_reminders(status: Optional[str] = "pending") -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        if status:
            cur = conn.execute("SELECT * FROM reminders WHERE status = ? ORDER BY due_at ASC", (status,))
        else:
            cur = conn.execute("SELECT * FROM reminders ORDER BY due_at ASC")
        return [dict(row) for row in cur.fetchall()]


# --- Notes Operations ---
def db_add_note(text: str, tags: str = "") -> Dict[str, Any]:
    note_id = f"note-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO notes (id, text, tags, created_at) VALUES (?, ?, ?, ?)",
            (note_id, text, tags, now),
        )
        conn.commit()
    return {"id": note_id, "text": text, "tags": tags, "created_at": now}


def db_list_notes(query: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        if query:
            cur = conn.execute("SELECT * FROM notes WHERE text LIKE ? OR tags LIKE ? ORDER BY created_at DESC", (f"%{query}%", f"%{query}%"))
        else:
            cur = conn.execute("SELECT * FROM notes ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]


# --- User Authentication & Personal History ---
import hashlib
import secrets


def hash_password(password: str) -> str:
    """Salt and hash a user password using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain password against a stored salt:hash string."""
    try:
        salt, h = stored_hash.split(":", 1)
        new_h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return secrets.compare_digest(h, new_h.hex())
    except Exception:
        return False


def db_create_user(username: str, password: str, email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Register a new user account."""
    user_id = f"usr-{uuid.uuid4().hex[:8]}"
    pwd_hash = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()
    clean_u = username.strip().lower()
    clean_e = (email or "").strip().lower() or None
    try:
        with get_db_connection() as conn:
            if clean_e:
                dup_email = conn.execute("SELECT 1 FROM users WHERE email = ? LIMIT 1", (clean_e,)).fetchone()
                if dup_email:
                    return None
            conn.execute(
                "INSERT INTO users (id, username, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, clean_u, clean_e, pwd_hash, now),
            )
            conn.commit()
        return {"id": user_id, "username": clean_u, "email": clean_e or "", "created_at": now}
    except sqlite3.IntegrityError:
        return None


def db_get_or_create_google_user(email: str, name: Optional[str] = None) -> Dict[str, Any]:
    """Get existing user by email or register a new user from Google OAuth."""
    import re
    clean_e = (email or "").strip().lower()
    if not clean_e:
        clean_e = "user@example.com"
    existing = db_get_user_by_username(clean_e)
    if existing:
        return {"id": existing["id"], "username": existing["username"], "email": existing.get("email") or clean_e}

    # Generate clean unique username
    base_u = (name or clean_e.split("@")[0]).strip().lower().replace(" ", "")
    base_u = re.sub(r"[^a-z0-9_]", "", base_u) or "user"
    candidate_u = base_u
    suffix = 1
    while db_get_user_by_username(candidate_u):
        candidate_u = f"{base_u}{suffix}"
        suffix += 1

    random_pwd = secrets.token_urlsafe(24)
    user = db_create_user(username=candidate_u, password=random_pwd, email=clean_e)
    if user:
        return user
    found = db_get_user_by_username(clean_e)
    if found:
        return {"id": found["id"], "username": found["username"], "email": found.get("email") or clean_e}
    return {"id": f"usr-{uuid.uuid4().hex[:8]}", "username": candidate_u, "email": clean_e}


def db_get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Lookup user by username or email."""
    clean = username.strip().lower()
    with get_db_connection() as conn:
        cur = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (clean, clean))
        row = cur.fetchone()
        return dict(row) if row else None


def db_get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Lookup user profile by ID."""
    with get_db_connection() as conn:
        cur = conn.execute("SELECT id, username, email, created_at FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def db_create_session_token(user_id: str) -> str:
    """Generate and store an authentication token."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO user_tokens (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, now),
        )
        conn.commit()
    return token


def db_get_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """Resolve user from auth token."""
    if not token:
        return None
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT u.id, u.username, u.email, u.created_at FROM users u JOIN user_tokens t ON u.id = t.user_id WHERE t.token = ?",
            (token,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def db_delete_session_token(token: str) -> bool:
    """Invalidate session token on logout."""
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM user_tokens WHERE token = ?", (token,))
        conn.commit()
        return cur.rowcount > 0


def db_save_chat_turn(
    user_id: str,
    session_id: str,
    user_message: str,
    spoken_reply: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    latency_ms: float = 0.0,
) -> str:
    """Save a conversational turn into the user's permanent history."""
    turn_id = f"hist-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    tools_json = json.dumps(tool_calls or [])
    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO chat_history 
               (id, user_id, session_id, user_message, spoken_reply, tool_calls, latency_ms, created_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (turn_id, user_id, session_id, user_message, spoken_reply, tools_json, latency_ms, now),
        )
        conn.commit()
    return turn_id


def db_list_chat_history(user_id: str, session_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve personal chat history for a user."""
    with get_db_connection() as conn:
        if session_id:
            cur = conn.execute(
                """SELECT * FROM chat_history 
                   WHERE user_id = ? AND session_id = ? 
                   ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                (user_id, session_id, limit),
            )
        else:
            cur = conn.execute(
                """SELECT * FROM chat_history 
                   WHERE user_id = ? 
                   ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                (user_id, limit),
            )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if r.get("tool_calls"):
                try:
                    r["tool_calls"] = json.loads(r["tool_calls"])
                except Exception:
                    r["tool_calls"] = []
            else:
                r["tool_calls"] = []
        return rows


def db_clear_chat_history(user_id: str, session_id: Optional[str] = None) -> bool:
    """Clear chat history for a user or session."""
    with get_db_connection() as conn:
        if session_id:
            cur = conn.execute("DELETE FROM chat_history WHERE user_id = ? AND session_id = ?", (user_id, session_id))
        else:
            cur = conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount > 0


def db_delete_chat_turn(turn_id: str, user_id: str) -> bool:
    """Delete a single chat turn from history."""
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM chat_history WHERE id = ? AND user_id = ?", (turn_id, user_id))
        conn.commit()
        return cur.rowcount > 0


def db_list_chat_sessions(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve chat conversations grouped by session_id for a user in a single query."""
    with get_db_connection() as conn:
        cur = conn.execute(
            """WITH ranked AS (
                SELECT
                    session_id,
                    user_message,
                    spoken_reply,
                    created_at,
                    rowid,
                    ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY created_at ASC, rowid ASC) AS rn_first,
                    ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY created_at DESC, rowid DESC) AS rn_last
                FROM chat_history
                WHERE user_id = ?
            )
            SELECT
                session_id,
                COUNT(*) AS turn_count,
                MIN(created_at) AS created_at,
                MAX(created_at) AS last_active,
                MAX(rowid) AS last_rowid,
                MAX(CASE WHEN rn_first = 1 THEN user_message ELSE '' END) AS title,
                MAX(CASE WHEN rn_last = 1 THEN spoken_reply ELSE '' END) AS last_message
            FROM ranked
            GROUP BY session_id
            ORDER BY last_active DESC, last_rowid DESC
            LIMIT ?""",
            (user_id, limit),
        )
        sessions = []
        for r in cur.fetchall():
            item = dict(r)
            item.pop("last_rowid", None)
            if not item.get("title"):
                item["title"] = "Conversation"
            sessions.append(item)
        return sessions


def db_get_session_turns(user_id: Optional[str] = None, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all turns for a specific chat session ordered chronologically.
    
    Supports:
      - db_get_session_turns(user_id, session_id)
      - db_get_session_turns(session_id)
      - db_get_session_turns(session_id=..., user_id=...)
    """
    if session_id is None and user_id is not None:
        session_id = user_id
        user_id = None

    with get_db_connection() as conn:
        if user_id and session_id:
            cur = conn.execute(
                """SELECT * FROM chat_history 
                   WHERE user_id = ? AND session_id = ? 
                   ORDER BY created_at ASC, rowid ASC""",
                (user_id, session_id),
            )
        elif session_id:
            cur = conn.execute(
                """SELECT * FROM chat_history 
                   WHERE session_id = ? 
                   ORDER BY created_at ASC, rowid ASC""",
                (session_id,),
            )
        elif user_id:
            cur = conn.execute(
                """SELECT * FROM chat_history 
                   WHERE user_id = ? 
                   ORDER BY created_at ASC, rowid ASC""",
                (user_id,),
            )
        else:
            return []
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if r.get("tool_calls"):
                try:
                    r["tool_calls"] = json.loads(r["tool_calls"])
                except Exception:
                    r["tool_calls"] = []
            else:
                r["tool_calls"] = []
        return rows


def db_delete_chat_session(user_id: Optional[str] = None, session_id: Optional[str] = None) -> bool:
    """Delete an entire chat session and all its turns from history."""
    if session_id is None and user_id is not None:
        session_id = user_id
        user_id = None

    with get_db_connection() as conn:
        if user_id and session_id:
            cur = conn.execute(
                "DELETE FROM chat_history WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            )
        elif session_id:
            cur = conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
        elif user_id:
            cur = conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        else:
            return False
        conn.commit()
        return cur.rowcount > 0


# --- OAuth Token Storage (Google / Gmail Integrations) ---
def db_save_user_oauth(
    user_id: str,
    email: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    provider: str = "google",
    token_expiry: Optional[str] = None,
) -> Dict[str, Any]:
    """Store or update OAuth credentials for a user."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        # Check existing
        cur = conn.execute(
            "SELECT id, refresh_token FROM user_oauth_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        row = cur.fetchone()
        if row:
            oauth_id = row["id"]
            # Preserve existing refresh token if not provided in refresh grant
            final_refresh = refresh_token or row["refresh_token"]
            conn.execute(
                """UPDATE user_oauth_tokens 
                   SET email = ?, access_token = ?, refresh_token = ?, token_expiry = ?, updated_at = ? 
                   WHERE id = ?""",
                (email, access_token, final_refresh, token_expiry, now, oauth_id),
            )
        else:
            oauth_id = f"oath-{uuid.uuid4().hex[:8]}"
            conn.execute(
                """INSERT INTO user_oauth_tokens 
                   (id, user_id, provider, email, access_token, refresh_token, token_expiry, created_at, updated_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (oauth_id, user_id, provider, email, access_token, refresh_token, token_expiry, now, now),
            )
        conn.commit()
    return {"id": oauth_id, "user_id": user_id, "provider": provider, "email": email}


def db_get_user_oauth(user_id: Optional[str] = None, provider: str = "google") -> Optional[Dict[str, Any]]:
    """Retrieve stored OAuth credentials strictly scoped to the requested user (no cross-user fallback).
    
    Resolution order:
    1. Exact user_id match
    2. Stripped legacy prefix (e.g. 'user-1' -> '1')
    3. User email match
    4. 'guest' row ONLY when user_id is None, '', or 'guest'
    """
    with get_db_connection() as conn:
        if user_id:
            uid_str = str(user_id).strip()
            cur = conn.execute(
                "SELECT * FROM user_oauth_tokens WHERE user_id = ? AND provider = ? ORDER BY updated_at DESC LIMIT 1",
                (uid_str, provider),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

            if uid_str.startswith("user-"):
                clean_uid = uid_str.replace("user-", "", 1)
                cur = conn.execute(
                    "SELECT * FROM user_oauth_tokens WHERE user_id = ? AND provider = ? ORDER BY updated_at DESC LIMIT 1",
                    (clean_uid, provider),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)

            if "@" in uid_str:
                cur = conn.execute(
                    "SELECT * FROM user_oauth_tokens WHERE email = ? AND provider = ? ORDER BY updated_at DESC LIMIT 1",
                    (uid_str, provider),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)

            if uid_str not in ("guest", ""):
                return None

        cur = conn.execute(
            "SELECT * FROM user_oauth_tokens WHERE user_id = 'guest' AND provider = ? ORDER BY updated_at DESC LIMIT 1",
            (provider,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def db_delete_user_oauth(user_id: Optional[str] = None, provider: str = "google") -> bool:
    """Disconnect / delete OAuth credentials strictly for the given user_id."""
    with get_db_connection() as conn:
        deleted = False
        if user_id:
            uid_str = str(user_id).strip()
            cur = conn.execute(
                "DELETE FROM user_oauth_tokens WHERE user_id = ? AND provider = ?",
                (uid_str, provider),
            )
            if cur.rowcount > 0:
                deleted = True
            if uid_str.startswith("user-"):
                cur = conn.execute(
                    "DELETE FROM user_oauth_tokens WHERE user_id = ? AND provider = ?",
                    (uid_str.replace("user-", "", 1), provider),
                )
                if cur.rowcount > 0:
                    deleted = True
        else:
            cur = conn.execute(
                "DELETE FROM user_oauth_tokens WHERE user_id = 'guest' AND provider = ?",
                (provider,),
            )
            deleted = cur.rowcount > 0

        conn.commit()
        return deleted


# Auto-initialize database on import
init_db()


# --- User Email Profile (Custom Sender Credentials, e.g. Krish) ---
def db_save_user_email_profile(
    user_id: str = "krish",
    sender_name: str = "Krish",
    sender_email: str = "",
    sender_password: Optional[str] = None,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
) -> Dict[str, Any]:
    """Store or update personal sender email profile credentials for a user (e.g. Krish)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_email_profiles (
                user_id TEXT PRIMARY KEY,
                sender_name TEXT NOT NULL,
                sender_email TEXT NOT NULL,
                sender_password TEXT,
                smtp_host TEXT DEFAULT 'smtp.gmail.com',
                smtp_port INTEGER DEFAULT 587,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        cur = conn.execute("SELECT user_id, sender_password FROM user_email_profiles WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        final_password = sender_password if sender_password is not None else (row["sender_password"] if row else None)
        if row:
            conn.execute(
                """UPDATE user_email_profiles 
                   SET sender_name = ?, sender_email = ?, sender_password = ?, smtp_host = ?, smtp_port = ?, updated_at = ?
                   WHERE user_id = ?""",
                (sender_name, sender_email, final_password, smtp_host, smtp_port, now, user_id),
            )
        else:
            conn.execute(
                """INSERT INTO user_email_profiles 
                   (user_id, sender_name, sender_email, sender_password, smtp_host, smtp_port, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, sender_name, sender_email, final_password, smtp_host, smtp_port, now, now),
            )
        conn.commit()
    return {
        "user_id": user_id,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "has_password": bool(final_password),
    }


def db_get_user_email_profile(user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve stored personal email sender profile strictly scoped to user (guest may read default owner profile)."""
    uid = (user_id or "guest").strip() or "guest"
    with get_db_connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_email_profiles (
                user_id TEXT PRIMARY KEY,
                sender_name TEXT NOT NULL,
                sender_email TEXT NOT NULL,
                sender_password TEXT,
                smtp_host TEXT DEFAULT 'smtp.gmail.com',
                smtp_port INTEGER DEFAULT 587,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        cur = conn.execute("SELECT * FROM user_email_profiles WHERE user_id = ? LIMIT 1", (uid,))
        row = cur.fetchone()
        if not row and uid in ("guest", ""):
            cur = conn.execute("SELECT * FROM user_email_profiles WHERE user_id = 'krish' LIMIT 1")
            row = cur.fetchone()
        return dict(row) if row else None


# --- Execution Tracing & Observability Operations ---
def db_record_trace(
    trace_id: str,
    session_id: str,
    name: str,
    run_type: str = "chain",
    start_time: float = 0.0,
    end_time: Optional[float] = None,
    latency_ms: Optional[float] = None,
    status: str = "success",
    inputs: Any = None,
    outputs: Any = None,
    metadata: Any = None,
    user_id: str = "guest",
) -> Dict[str, Any]:
    """Persist an execution trace span to SQLite for local observability."""
    import json
    now = datetime.now(timezone.utc).isoformat()
    inp_json = json.dumps(inputs) if inputs is not None else "{}"
    out_json = json.dumps(outputs) if outputs is not None else "{}"
    meta_json = json.dumps(metadata) if metadata is not None else "{}"

    with get_db_connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS execution_traces (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'guest',
                name TEXT NOT NULL,
                run_type TEXT NOT NULL DEFAULT 'chain',
                start_time REAL NOT NULL,
                end_time REAL,
                latency_ms REAL,
                status TEXT NOT NULL DEFAULT 'running',
                inputs_json TEXT,
                outputs_json TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """INSERT OR REPLACE INTO execution_traces 
               (id, session_id, user_id, name, run_type, start_time, end_time, latency_ms, status, inputs_json, outputs_json, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trace_id, session_id, user_id, name, run_type, start_time, end_time, latency_ms, status, inp_json, out_json, meta_json, now),
        )
        conn.commit()

    return {
        "id": trace_id,
        "session_id": session_id,
        "name": name,
        "run_type": run_type,
        "latency_ms": latency_ms,
        "status": status,
        "created_at": now,
    }


def db_list_traces(limit: int = 50, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve execution traces ordered by creation time descending."""
    import json
    with get_db_connection() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS execution_traces (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'guest',
                name TEXT NOT NULL,
                run_type TEXT NOT NULL DEFAULT 'chain',
                start_time REAL NOT NULL,
                end_time REAL,
                latency_ms REAL,
                status TEXT NOT NULL DEFAULT 'running',
                inputs_json TEXT,
                outputs_json TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        if session_id:
            cur = conn.execute(
                "SELECT * FROM execution_traces WHERE session_id = ? ORDER BY start_time DESC, created_at DESC LIMIT ?",
                (session_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM execution_traces ORDER BY start_time DESC, created_at DESC LIMIT ?",
                (limit,),
            )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["trace_id"] = r.get("id")
            for k in ["inputs_json", "outputs_json", "metadata_json"]:
                if r.get(k):
                    try:
                        r[k.replace("_json", "")] = json.loads(r[k])
                    except Exception:
                        r[k.replace("_json", "")] = r[k]
        return rows


def db_get_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single execution trace by ID."""
    import json
    with get_db_connection() as conn:
        cur = conn.execute("SELECT * FROM execution_traces WHERE id = ? LIMIT 1", (trace_id,))
        row = cur.fetchone()
        if not row:
            return None
        r = dict(row)
        r["trace_id"] = r.get("id")
        for k in ["inputs_json", "outputs_json", "metadata_json"]:
            if r.get(k):
                try:
                    r[k.replace("_json", "")] = json.loads(r[k])
                except Exception:
                    r[k.replace("_json", "")] = r[k]
        return r


def db_clear_traces() -> bool:
    """Clear all stored execution traces."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM execution_traces")
        conn.commit()
    return True


