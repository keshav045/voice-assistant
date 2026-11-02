"""In-process conversation session store.

Keeps the last N messages per session_id. Older messages are summarized
and stored as a single 'assistant' context block to save tokens.
"""

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

# Max messages to keep in full; older ones get summarized
MAX_FULL_MESSAGES = 10
# Max sessions to hold in memory at once (LRU eviction)
MAX_SESSIONS = 200

# session_id -> {"messages": [...], "summary": str | None, "last_access": float}
_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _evict_if_needed() -> None:
    """Evict the least-recently-used session when over capacity."""
    if len(_SESSIONS) > MAX_SESSIONS:
        oldest = min(_SESSIONS, key=lambda sid: _SESSIONS[sid]["last_access"])
        del _SESSIONS[oldest]


def get_session(session_id: str) -> Dict[str, Any]:
    """Return or create the session dict for a given session_id."""
    if session_id not in _SESSIONS:
        _evict_if_needed()
        _SESSIONS[session_id] = {
            "messages": [],
            "summary": None,
            "last_access": time.time(),
        }
    _SESSIONS[session_id]["last_access"] = time.time()
    return _SESSIONS[session_id]


def get_messages_for_prompt(session_id: str) -> List[Dict[str, str]]:
    """Return the message list to prepend before the current user turn.

    If there is a conversation summary, it is injected as a single system
    context message first, followed by the recent full messages.
    """
    sess = get_session(session_id)
    result: List[Dict[str, str]] = []

    if sess["summary"]:
        result.append({
            "role": "system",
            "content": f"[Conversation so far]\n{sess['summary']}",
        })

    result.extend(sess["messages"])
    return result


def add_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    """Append a completed user→assistant turn to the session.

    When the message count exceeds MAX_FULL_MESSAGES, the oldest half is
    collapsed into a plain-text summary and discarded.
    """
    sess = get_session(session_id)
    sess["messages"].append({"role": "user", "content": user_text})
    sess["messages"].append({"role": "assistant", "content": assistant_text})

    # Compact old messages into summary when buffer is full
    if len(sess["messages"]) > MAX_FULL_MESSAGES * 2:
        half = MAX_FULL_MESSAGES  # number of messages to collapse
        old = sess["messages"][:half]
        sess["messages"] = sess["messages"][half:]

        # Build simple text summary of old messages
        lines = []
        for m in old:
            prefix = "User" if m["role"] == "user" else "Assistant"
            lines.append(f"{prefix}: {m['content'][:200]}")

        new_summary = "\n".join(lines)
        if sess["summary"]:
            sess["summary"] = sess["summary"] + "\n" + new_summary
        else:
            sess["summary"] = new_summary

        # Cap summary length
        if len(sess["summary"]) > 2000:
            sess["summary"] = sess["summary"][-2000:]


def clear_session(session_id: str) -> None:
    """Clear all messages and summary for a session."""
    if session_id in _SESSIONS:
        del _SESSIONS[session_id]

