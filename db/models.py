"""Database access and models for Personal Voice Assistant."""

import sqlite3
import os
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get(
    "DB_PATH",
    os.environ.get(
        "SQLITE_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "voice_assistant.db"),
    ),
)
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db_connection() -> sqlite3.Connection:
    """Return a production-ready connection to the SQLite database with WAL mode and foreign keys enabled."""
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    return conn


def init_db() -> None:
    """Initialize database tables from schema.sql."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with get_db_connection() as conn:
        conn.executescript(schema_sql)
        conn.commit()


# --- Task Operations ---
def db_add_task(title: str, due_at: Optional[str] = None) -> Dict[str, Any]:
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (id, title, due_at, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (task_id, title, due_at, now),
        )
        conn.commit()
    return {"id": task_id, "title": title, "due_at": due_at, "status": "pending", "created_at": now}


def db_list_tasks(status: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        if status:
            cur = conn.execute("SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cur = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]


def db_complete_task(task_id: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cur = conn.execute(
            "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ? OR title LIKE ?",
            (now, task_id, f"%{task_id}%"),
        )
        conn.commit()
        return cur.rowcount > 0


# --- Memory Operations ---
def db_add_fact(fact: str, category: str = "general") -> Dict[str, Any]:
    fact_id = f"fact-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO memory_facts (id, fact, category, created_at, last_used_at) VALUES (?, ?, ?, ?, ?)",
            (fact_id, fact, category, now, now),
        )
        conn.commit()
    return {"id": fact_id, "fact": fact, "category": category, "created_at": now}


def db_list_facts(category: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        if category:
            cur = conn.execute("SELECT * FROM memory_facts WHERE category = ? ORDER BY created_at DESC", (category,))
        else:
            cur = conn.execute("SELECT * FROM memory_facts ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]


def db_forget_fact(fact_query: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM memory_facts WHERE id = ? OR fact LIKE ?",
            (fact_query, f"%{fact_query}%"),
        )
        conn.commit()
        return cur.rowcount > 0


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
            conn.execute(
                "INSERT INTO users (id, username, email, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, clean_u, clean_e, pwd_hash, now),
            )
            conn.commit()
        return {"id": user_id, "username": username.strip(), "email": clean_e or "", "created_at": now}
    except sqlite3.IntegrityError:
        return None


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
                   ORDER BY created_at DESC LIMIT ?""",
                (user_id, session_id, limit),
            )
        else:
            cur = conn.execute(
                """SELECT * FROM chat_history 
                   WHERE user_id = ? 
                   ORDER BY created_at DESC LIMIT ?""",
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
    """Retrieve chat conversations grouped by session_id for a user."""
    with get_db_connection() as conn:
        cur = conn.execute(
            """SELECT 
                session_id,
                COUNT(*) as turn_count,
                MIN(created_at) as created_at,
                MAX(created_at) as last_active
               FROM chat_history 
               WHERE user_id = ? 
               GROUP BY session_id 
               ORDER BY last_active DESC 
               LIMIT ?""",
            (user_id, limit),
        )
        sessions = [dict(r) for r in cur.fetchall()]

        for s in sessions:
            cur_first = conn.execute(
                """SELECT user_message FROM chat_history 
                   WHERE user_id = ? AND session_id = ? 
                   ORDER BY created_at ASC LIMIT 1""",
                (user_id, s["session_id"]),
            )
            row_first = cur_first.fetchone()
            s["title"] = row_first["user_message"] if row_first else "Conversation"

            cur_last = conn.execute(
                """SELECT spoken_reply FROM chat_history 
                   WHERE user_id = ? AND session_id = ? 
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id, s["session_id"]),
            )
            row_last = cur_last.fetchone()
            s["last_message"] = row_last["spoken_reply"] if row_last else ""

        return sessions


def db_get_session_turns(user_id: str, session_id: str) -> List[Dict[str, Any]]:
    """Retrieve all turns for a specific chat session ordered chronologically."""
    with get_db_connection() as conn:
        cur = conn.execute(
            """SELECT * FROM chat_history 
               WHERE user_id = ? AND session_id = ? 
               ORDER BY created_at ASC""",
            (user_id, session_id),
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


def db_delete_chat_session(user_id: str, session_id: str) -> bool:
    """Delete an entire chat session and all its turns from history."""
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM chat_history WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
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


def db_get_user_oauth(user_id: str, provider: str = "google") -> Optional[Dict[str, Any]]:
    """Retrieve stored OAuth credentials for a user."""
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM user_oauth_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def db_delete_user_oauth(user_id: str, provider: str = "google") -> bool:
    """Disconnect / delete OAuth credentials for a user."""
    with get_db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM user_oauth_tokens WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        conn.commit()
        return cur.rowcount > 0


# Auto-initialize database on import
init_db()

