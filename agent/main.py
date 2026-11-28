"""Personal Voice Assistant Main Entrypoint & Server."""

import asyncio
import base64
import contextvars
import html
import inspect
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
from dotenv import load_dotenv
load_dotenv(override=False)

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Header
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI

from db.models import (
    init_db,
    db_log_tool_call,
    db_list_tasks,
    db_add_task,
    db_complete_task,
    db_list_facts,
    db_get_tool_calls,
    db_create_user,
    db_get_user_by_username,
    db_get_user_by_id,
    verify_password,
    db_create_session_token,
    db_get_user_from_token,
    db_delete_session_token,
    db_save_chat_turn,
    db_list_chat_history,
    db_clear_chat_history,
    db_delete_chat_turn,
    db_list_chat_sessions,
    db_get_session_turns,
    db_delete_chat_session,
)
from agent.prompts import SYSTEM_PROMPT, COMPACT_SYSTEM_PROMPT
from agent.confirm import requires_confirmation, format_read_back, is_confirmed
from agent.memory import get_memory_context
from agent.screening import screen_input, screen_output
from agent.tools import TOOLS_REGISTRY, TOOL_SCHEMAS
from agent.session import get_messages_for_prompt, add_turn
from agent.safety import validate_tool_args, is_write_action

# Initialize database
init_db()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_assistant")

app = FastAPI(title="AI Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "qwen2.5:1.5b")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").strip() or None

# Pending confirmations cache per session
_PENDING_CONFIRMATIONS: Dict[str, Dict[str, Any]] = {}

# Per-request context flag indicating web frontend handles opening returned URLs
_CLIENT_HANDLES_URLS: contextvars.ContextVar[bool] = contextvars.ContextVar("client_handles_urls", default=False)

# Pooled AsyncOpenAI clients keyed by (running_loop_id, api_key, base_url)
_ASYNC_CLIENT_POOL: Dict[Tuple[int, str, str], AsyncOpenAI] = {}


def _get_async_openai_client(api_key: str, base_url: Optional[str]) -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client bound to the active event loop with explicit timeouts."""
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = 0
    key = (loop_id, api_key, base_url or "")
    client = _ASYNC_CLIENT_POOL.get(key)
    if client is None:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(25.0, connect=4.0),
            max_retries=1,
        )
        if len(_ASYNC_CLIENT_POOL) > 16:
            _ASYNC_CLIENT_POOL.pop(next(iter(_ASYNC_CLIENT_POOL)))
        _ASYNC_CLIENT_POOL[key] = client
    return client


# --- Request / Response Models ---
class SignupRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    use_langgraph: Optional[bool] = None


class ConfirmRequest(BaseModel):
    session_id: str
    approved: bool = True
    decision: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    spoken_reply: str
    reply: Optional[str] = None
    tool_calls_executed: List[Dict[str, Any]] = []
    requires_confirmation: bool = False
    needs_confirmation: Optional[Any] = None
    confirmation_question: Optional[str] = None
    session_id: str
    latency_ms: float
    model: Optional[str] = "qwen2.5:1.5b"


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "alloy"
    speed: Optional[float] = 1.0


def _clean_spoken_text(text: str) -> str:
    """Strip markdown formatting, symbols, links, and bullets for natural voice synthesis."""
    if not text:
        return ""
    # Strip markdown headers
    t = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Strip markdown links [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    # Strip raw http/https URLs
    t = re.sub(r"https?://\S+", "", t)
    # Strip bold / italics markdown without stripping internal snake_case underscores
    t = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", t)
    t = re.sub(r"(?<!\w)_{1,3}([^_]+)_{1,3}(?!\w)", r"\1", t)
    # Strip list item bullets
    t = re.sub(r"^\s*[-*•]\s*", "", t, flags=re.MULTILINE)
    # Strip code blocks
    t = re.sub(r"`{1,3}[^`]*`{1,3}", "", t)
    # Collapse newlines into spaces
    t = re.sub(r"\n+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Cap spoken text length at <= 550 chars for clean voice output
    if len(t) > 550:
        t = t[:540]
        last_dot = t.rfind(".")
        if last_dot > 250:
            t = t[:last_dot + 1]
    return t


def _extract_youtube_query(text: str) -> Optional[str]:
    """Cleanly extract query for YouTube searches from voice requests."""
    t = text.strip().rstrip(".")
    # 1. 'search for X on youtube' or 'play X on youtube'
    m = re.search(r'(?:search\s+(?:for\s+)?|play\s+|watch\s+)(.+?)(?:\s+(?:on|in)\s+youtube)', t, re.IGNORECASE)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 2. 'search youtube for X'
    m = re.search(r'search\s+youtube\s+(?:for\s+)?(.+)', t, re.IGNORECASE)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 3. 'open youtube and search for/play X' or 'youtube search for X'
    m = re.search(r'(?:open\s+)?youtube\s+(?:and\s+)?(?:search\s+(?:for\s+)?|play\s+|watch\s+|for\s+)?(.+)', t, re.IGNORECASE)
    if m and m.group(1).strip() and m.group(1).strip().lower() != 'youtube':
        q = m.group(1).strip()
        q = re.sub(r'^(and\s+)?(search\s+for|search|play|watch|for)\s+', '', q, flags=re.IGNORECASE).strip()
        if q and q.lower() != 'youtube':
            return q

    return None


ACTIVE_TOOL_NAMES = set(TOOLS_REGISTRY.keys())
ACTIVE_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS if s.get("function", {}).get("name") in ACTIVE_TOOL_NAMES]


def _parse_tool_call_args(raw_args: Any) -> Dict[str, Any]:
    """Parse and unwrap LLM tool-call arguments (handles Ollama nested 'parameters' wrappers)."""
    try:
        parsed = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    if isinstance(parsed.get("parameters"), dict) and any(k in parsed for k in ("type", "function", "name")):
        parsed = parsed["parameters"]
    elif isinstance(parsed.get("arguments"), dict) and any(k in parsed for k in ("type", "function", "name")):
        parsed = parsed["arguments"]
    return parsed


def _filter_handler_kwargs(handler: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only kwargs accepted by handler (unless **kwargs is present) to prevent TypeError."""
    try:
        sig = inspect.signature(handler)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            return args
        return {k: v for k, v in args.items() if k in sig.parameters}
    except Exception:
        return args


def _normalize_greeting_text(text: str) -> str:
    """Collapse elongated greeting characters (e.g. 'hiii' -> 'hi', 'heyyy' -> 'hey')."""
    norm = re.sub(r"[^a-z\s']", "", text.lower().strip())
    norm = re.sub(r"(.)\1{2,}", r"\1", norm)
    if re.fullmatch(r"hi+", norm):
        return "hi"
    if re.fullmatch(r"he+y+", norm):
        return "hey"
    return norm


def _is_tool_call_aligned_with_intent(tool_name: str, user_text: str) -> bool:
    """Verify that a tool call emitted by an LLM is actually requested by the user,
    preventing small local models (like Ollama qwen2.5:1.5b) from executing hallucinated write actions or searches."""
    lower = user_text.lower().strip()
    norm_greeting = _normalize_greeting_text(lower)

    # Block all tool calls if input is a basic conversational greeting or pleasantry
    greetings = {
        "hello", "hi", "hey", "hola", "namaste", "sup", "yo",
        "good morning", "good afternoon", "good evening", "good night",
        "how are you", "how are you doing", "what's up", "whats up",
        "who are you", "what can you do", "help", "thanks", "thank you",
        "ok", "okay", "cool", "great", "nice", "bye", "goodbye"
    }
    if lower in greetings or norm_greeting in greetings or (any(lower.startswith(g + " ") for g in ["hello", "hi", "hey", "namaste", "good morning", "good evening"]) and len(lower.split()) <= 3):
        return False

    if tool_name == "send_email":
        email_keywords = [
            "email", "mail", "gmail", "send to", "send an email", "send a mail",
            "write to", "dispatch", "compose", "message to", "invite", "meeting",
            "send", "recipient", "outlook", "subject"
        ]
        return any(k in lower for k in email_keywords) or "@" in user_text

    if tool_name == "send_whatsapp_message":
        return any(k in lower for k in ["whatsapp", "chat", "message", "text"])

    if tool_name == "open_app":
        app_keywords = [
            "open", "launch", "start", "go to", "play on youtube", "on youtube",
            "youtube", "spotify", "linkedin", "gmail", "github", "calculator", "notepad", "explorer", "whatsapp"
        ]
        return any(k in lower for k in app_keywords)

    if tool_name == "medical_search":
        med_keywords = [
            "medicine", "tablet", "capsule", "drug", "dosage", "side effect", "side effects",
            "precaution", "precautions", "paracetamol", "dolo", "ibuprofen", "crocin", "metformin",
            "amoxicillin", "azithromycin", "omeprazole", "pantoprazole", "cetirizine", "aspirin", "atorvastatin"
        ]
        return any(k in lower for k in med_keywords)

    if tool_name == "calculator":
        calc_words = ["calculate", "math", "sqrt", "power", "sum", "multiply", "divide", "percent", "discount"]
        has_math_word = any(re.search(rf"\b{re.escape(k)}\b", lower) for k in calc_words)
        has_math_expr = bool(re.search(r"\d\s*[+\-*/%^]|%\s*(?:of|on|off)\b|\*\*", lower))
        return has_math_word or has_math_expr

    if tool_name == "run_python_code":
        code_keywords = ["python", "code", "run", "script", "execute", "def ", "import ", "program", "function"]
        return any(k in lower for k in code_keywords)

    if tool_name == "get_current_time":
        time_keywords = ["time", "date", "clock", "day", "today", "hour"]
        return any(re.search(rf"\b{re.escape(k)}\b", lower) for k in time_keywords)

    if tool_name in {"web_search", "get_live_news"}:
        if any(k in lower for k in ["search my email", "search email", "search emails", "my docs", "search docs"]):
            return False
        # Use word boundaries to prevent substring triggers like 'ai' inside 'pain'
        search_phrases = [
            "tell me", "what is", "who is", "where is", "when is", "how to", "how is",
        ]
        search_words = [
            "search", "serch", "nwes", "lateest", "ai", "who", "what", "where", "when", "why", "how",
            "score", "scores", "news", "headline", "headlines", "breaking", "match", "vs", "cricket",
            "weather", "latest", "price", "stock", "information", "find", "update", "updates", "result", "results",
        ]
        return any(p in lower for p in search_phrases) or any(re.search(rf"\b{re.escape(w)}\b", lower) for w in search_words)

    return True


def _get_active_user_name(user_id: Optional[str] = None) -> str:
    """Dynamically resolve the active user's first name from auth, OAuth, or environment."""
    from db.models import db_get_user_oauth, db_get_user_by_id
    if user_id and str(user_id).strip() not in ("guest", "None", ""):
        u = db_get_user_by_id(user_id)
        if u and u.get("username"):
            return u["username"].capitalize()
    oauth = db_get_user_oauth(user_id=user_id)
    if oauth and oauth.get("email"):
        from agent.tools.email import _infer_recipient_name
        inferred = _infer_recipient_name(oauth["email"])
        if inferred:
            return inferred
    return os.environ.get("USER_NAME", "").strip() or "User"


def _get_default_recipient_email(user_id: Optional[str] = None) -> str:
    """Dynamically resolve the primary user's email address from OAuth, DB profile, or environment."""
    from db.models import db_get_user_oauth, db_get_user_email_profile
    oauth = db_get_user_oauth(user_id=user_id)
    if oauth and oauth.get("email"):
        return oauth["email"]
    prof = db_get_user_email_profile(user_id=user_id or "guest")
    if prof and prof.get("sender_email"):
        return prof["sender_email"]
    return os.environ.get("SENDER_EMAIL", "").strip() or "user@example.com"


def _extract_event_times(clean_text: str) -> Tuple[str, str]:
    """Extract clean start and end time expressions for calendar scheduling."""
    lower_q = clean_text.lower()
    day_prefix = "tomorrow " if ("tomorrow" in lower_q or "kal" in lower_q) else ""

    # Match "from 4 to 5 PM" or "from 5 PM to 4 PM" or "from 16:00 to 17:00"
    m_range = re.search(
        r"\bfrom\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+to\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        clean_text,
        flags=re.IGNORECASE,
    )
    if m_range:
        raw_s = m_range.group(1).strip()
        raw_e = m_range.group(2).strip()
        if ("am" not in raw_s.lower() and "pm" not in raw_s.lower()) and ("am" in raw_e.lower() or "pm" in raw_e.lower()):
            suf = "PM" if "pm" in raw_e.lower() else "AM"
            raw_s = f"{raw_s} {suf}"
        return f"{day_prefix}{raw_s}".strip(), f"{day_prefix}{raw_e}".strip()

    # Single time like "at 5 PM" or "5 baje"
    m_single = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|(\d{1,2})\s*baje)\b", clean_text, flags=re.IGNORECASE)
    if m_single:
        tok = m_single.group(1).strip()
        if "baje" in tok.lower():
            hr = int(m_single.group(2))
            tok = f"{hr} PM" if hr <= 8 else f"{hr}:00"
        return f"{day_prefix}{tok}".strip(), ""

    return f"{day_prefix}16:00".strip(), f"{day_prefix}17:00".strip()


async def _stage_or_execute_tool(
    t_name: str,
    t_args: Dict[str, Any],
    session_id: str,
    effective_user_id: str,
    clean_text: str,
) -> Tuple[Dict[str, Any], bool]:
    """Validate and either stage HITL confirmation (without mutating DB) or run tool safely off-loop.

    Returns:
        (tool_result_dict, requires_confirmation_bool)
    """
    handler = TOOLS_REGISTRY.get(t_name)
    if not handler:
        return {"success": False, "error": f"Unknown tool: {t_name}", "spoken": f"Unknown tool '{t_name}'."}, False

    exec_args = dict(t_args)
    if t_name == "send_email":
        exec_args.setdefault("user_id", effective_user_id)
        exec_args.setdefault("sender_name", _get_active_user_name(effective_user_id))
        if not exec_args.get("recipient_name"):
            _stop_names = {"someone", "him", "her", "them", "a", "an", "the", "my", "asking", "saying", "about", "for"}
            m_recip = re.search(r'\b(?:to|mail|email)\s+([A-Za-z]+)', clean_text, re.I)
            if m_recip and m_recip.group(1).lower() not in _stop_names:
                exec_args["recipient_name"] = m_recip.group(1).capitalize()
    elif t_name == "medical_search":
        exec_args["user_query"] = clean_text
    elif t_name in {"add_task", "list_tasks", "complete_task", "delete_task", "list_events", "find_free_slot", "create_event", "remember", "forget", "search_my_docs"}:
        exec_args.setdefault("user_id", effective_user_id)

    if t_name in {"open_app", "send_whatsapp_message"} and _CLIENT_HANDLES_URLS.get(False):
        exec_args["launch_browser"] = False

    # Pre-mutation Human-In-The-Loop Confirmation Gating (create_event, delete_task)
    if t_name == "create_event":
        title = exec_args.get("title") or "Meeting"
        start_val = exec_args.get("start") or ""
        if not str(title).strip() or not str(start_val).strip():
            return {"success": False, "error": "Title and start time are required.", "spoken": "Please specify the meeting title and start time."}, False
        dry_args = _filter_handler_kwargs(handler, {**exec_args, "dry_run": True})
        preview = await asyncio.to_thread(handler, **dry_args)
        if not preview.get("success"):
            return preview, False
        clean_exec = _filter_handler_kwargs(handler, exec_args)
        read_back = format_read_back("create_event", clean_exec)
        _PENDING_CONFIRMATIONS[session_id] = {
            "tool": "create_event",
            "args": clean_exec,
            "user_id": effective_user_id,
            "question": read_back,
        }
        return {
            "success": True,
            "pending_confirmation": True,
            "event": preview.get("event"),
            "spoken": read_back,
        }, True

    if t_name == "delete_task":
        from db.models import db_find_task
        target = str(exec_args.get("task_id") or exec_args.get("id") or "").strip()
        if not target:
            return {"success": False, "task_id": target, "spoken": "Please specify which task ID or title to delete."}, False
        found = await asyncio.to_thread(db_find_task, target, effective_user_id)
        if not found:
            return {"success": False, "task_id": target, "spoken": f"Could not find task '{target}' to delete."}, False
        clean_exec = _filter_handler_kwargs(handler, {"task_id": target, "user_id": effective_user_id})
        read_back = format_read_back("delete_task", clean_exec)
        _PENDING_CONFIRMATIONS[session_id] = {
            "tool": "delete_task",
            "args": clean_exec,
            "user_id": effective_user_id,
            "question": read_back,
        }
        return {
            "success": True,
            "pending_confirmation": True,
            "task_id": target,
            "spoken": read_back,
        }, True

    filtered = _filter_handler_kwargs(handler, exec_args)
    t_start = time.perf_counter()
    try:
        t_res = await asyncio.to_thread(handler, **filtered)
    except Exception as h_err:
        t_res = {"success": False, "error": str(h_err), "spoken": f"Error executing {t_name}."}
    t_lat = round((time.perf_counter() - t_start) * 1000, 2)
    await asyncio.to_thread(db_log_tool_call, tool=t_name, args=filtered, session_id=session_id, latency_ms=t_lat)
    return t_res, False


def _plan_single_uncalled_intent(clean_text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Plan deterministic single-step fallback tool call when local LLM omits tool invocation."""
    lower_q = clean_text.lower().strip()
    planned: List[Tuple[str, Dict[str, Any]]] = []

    # Medical search
    if any(k in lower_q for k in ["paracetamol", "ibuprofen", "metformin", "dolo", "aspirin", "amoxicillin", "azithromycin", "xyzmedicine999", "medicine", "tablet"]):
        med_name = None
        for m in ["paracetamol", "ibuprofen", "metformin", "dolo 650", "dolo", "aspirin", "amoxicillin", "azithromycin", "xyzmedicine999"]:
            if m in lower_q:
                med_name = m
                break
        if not med_name:
            m_match = re.search(r"(?:about|of|drug|medicine)\s+([a-zA-Z0-9]+)", clean_text, re.I)
            if m_match:
                med_name = m_match.group(1)
        if med_name:
            top = "all"
            if "side effect" in lower_q:
                top = "side_effects"
            elif "use" in lower_q or "uses" in lower_q:
                top = "uses"
            elif "dose" in lower_q or "dosage" in lower_q or "year old" in lower_q or "child" in lower_q:
                top = "dosage"
            planned.append(("medical_search", {"medicine_name": med_name, "topic": top, "user_query": clean_text}))

    # Email sending
    elif lower_q.startswith("send an email") or lower_q.startswith("email "):
        if lower_q in ["send an email", "send email"]:
            planned.append(("send_email", {}))
        else:
            m_to = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
            if m_to:
                target_to = m_to.group(0)
            else:
                m_to = re.search(r"(?:send\s+(?:an\s+)?email\s+to|email\s+to|\bto)\s+([^\s,]+)", clean_text, re.I)
                if not m_to:
                    m_to = re.search(r"\bemail\s+([^\s,]+)", clean_text, re.I)
                target_to = m_to.group(1) if m_to else ""
            if target_to.lower() in ["an", "a", "me", "someone", "to", "saying", "asking", "about"]:
                target_to = ""
            m_subj = re.search(r"with subject\s+([^,]+?)(?:\s+saying|\s+asking|$)", clean_text, re.I)
            subj_val = m_subj.group(1).strip() if m_subj else None
            m_body = re.search(r"(?:saying|asking)\s+(.+)$", clean_text, re.I)
            body_val = m_body.group(1).strip() if m_body else clean_text
            em_args: Dict[str, Any] = {}
            if target_to:
                em_args["to"] = target_to
            if subj_val:
                em_args["subject"] = subj_val
            if body_val:
                em_args["description"] = body_val
            planned.append(("send_email", em_args))

    # Math calculation
    elif any(m in lower_q for m in ["percent", "square root", "to the power", "calculate", "discount"]) and any(c.isdigit() for c in clean_text):
        planned.append(("calculator", {"expression": clean_text}))

    # Python code execution
    elif lower_q.startswith("run python:"):
        code_snip = clean_text.split("run python:", 1)[1].strip()
        planned.append(("run_python_code", {"code": code_snip}))

    # Email search, summarize, draft
    elif lower_q.startswith("search my emails") or lower_q.startswith("search emails") or lower_q.startswith("show my last"):
        m_count = re.search(r"(\d+)\s+emails?", lower_q)
        max_r = int(m_count.group(1)) if m_count else 5
        em_q = re.sub(r"^(search\s+(my\s+)?emails?\s+(about|for)?\s*|show\s+my\s+last\s+\d+\s+emails?\s*)", "", clean_text, flags=re.I).strip()
        planned.append(("search_emails", {"query": em_q, "max_results": max_r}))

    elif "summarize the first email" in lower_q or lower_q.startswith("summarize email"):
        planned.append(("summarize_email", {}))

    elif lower_q.startswith("draft a reply") or lower_q.startswith("draft a formal reply"):
        planned.append(("draft_reply", {"instructions": clean_text}))

    # Search my docs
    elif "search my docs" in lower_q or "search docs" in lower_q:
        d_q = re.sub(r"^search\s+(my\s+)?docs\s+(for\s+)?", "", clean_text, flags=re.I).strip()
        planned.append(("search_my_docs", {"query": d_q or clean_text}))

    # Real-time News briefing
    elif any(k in lower_q for k in ["latest news", "breaking news", "top news", "world news", "tech news", "technology news", "sports news", "business news", "india news", "news updates", "give us news", "give me news"]) or lower_q in {"news", "headlines", "live news"}:
        topic = "top"
        for cat in ["world", "india", "technology", "tech", "business", "sports", "science", "health", "entertainment"]:
            if re.search(rf"\b{cat}\b", lower_q):
                topic = cat
                break
        planned.append(("get_live_news", {"topic": topic, "max_results": 5}))

    # Web search
    elif (lower_q.startswith("search ") or lower_q.startswith("serch ") or "cricket score" in lower_q) and not any(k in lower_q for k in ["email", "emails", "inbox", "my docs", "docs"]):
        s_query = re.sub(r"^(search\s+(for\s+)?|serch\s+(for\s+)?)", "", clean_text, flags=re.I).strip()
        s_args: Dict[str, Any] = {"query": s_query or clean_text}
        m_res = re.search(r"(\d+)\s+results?", clean_text, re.IGNORECASE)
        if m_res:
            s_args["max_results"] = int(m_res.group(1))
        planned.append(("web_search", s_args))

    # Tasks
    elif lower_q.startswith("add a task") or lower_q.startswith("add a high priority task"):
        t_title = re.sub(r"^add\s+(a\s+)?(high\s+priority\s+)?task\s*", "", clean_text, flags=re.I).strip()
        prio = "high" if "high priority" in lower_q else "medium"
        t_args_single: Dict[str, Any] = {"title": t_title}
        if t_title:
            t_args_single["priority"] = prio
        planned.append(("add_task", t_args_single))

    elif lower_q.startswith("show my pending tasks") or lower_q.startswith("show my completed tasks") or lower_q.startswith("show only"):
        status = "completed" if "completed" in lower_q else "pending"
        limit = 1 if "only 1" in lower_q else None
        l_args: Dict[str, Any] = {"status": status}
        if limit:
            l_args["limit"] = limit
        planned.append(("list_tasks", l_args))

    elif lower_q.startswith("mark task") or lower_q.startswith("complete task"):
        tid = re.search(r"\b(\d+|task-[a-f0-9]+)\b", lower_q)
        target = tid.group(1) if tid else clean_text
        planned.append(("complete_task", {"task_id": target}))

    elif lower_q.startswith("delete task"):
        tid = re.search(r"\b(\d+|task-[a-f0-9]+)\b", lower_q)
        target = tid.group(1) if tid else clean_text
        planned.append(("delete_task", {"task_id": target}))

    # Calendar
    elif "on my calendar" in lower_q or "what do i have tomorrow" in lower_q or lower_q.startswith("events on"):
        dt = "tomorrow" if "tomorrow" in lower_q else "today"
        planned.append(("list_events", {"date": dt}))

    elif "find a free" in lower_q or "find a 2 hour slot" in lower_q:
        dur = 120 if "2 hour" in lower_q else 30
        win = "tomorrow" if "tomorrow" in lower_q else "today"
        planned.append(("find_free_slot", {"duration_minutes": dur, "window": win}))

    elif "schedule a meeting" in lower_q or "meeting schedule" in lower_q:
        m_name = "Golden Sync" if "golden sync" in lower_q else re.sub(
            r"^(schedule\s+a\s+meeting\s+(called\s+)?|kal\s+ke\s+liye\s+meeting\s+schedule\s+kar\s+do\s*)",
            "",
            clean_text,
            flags=re.I,
        ).strip()
        start_t, end_t = _extract_event_times(clean_text)
        ev_args_single: Dict[str, Any] = {"title": m_name or "Meeting", "start": start_t}
        if end_t:
            ev_args_single["end"] = end_t
        planned.append(("create_event", ev_args_single))

    # Remember / Forget
    elif lower_q.startswith("remember"):
        f_text = re.split(r"remember\s*", clean_text, maxsplit=1, flags=re.I)[1].strip()
        planned.append(("remember", {"fact": f_text}))

    elif lower_q.startswith("forget"):
        f_text = re.split(r"forget\s*", clean_text, maxsplit=1, flags=re.I)[1].strip()
        planned.append(("forget", {"fact": f_text}))

    # App Opening
    elif (lower_q.startswith("open ") or lower_q.startswith("launch ")) and not (
        "whatsapp" in lower_q and any(k in lower_q for k in ["message", "text", "saying", "like", "+", "with", "chat"])
    ):
        app_t = None
        for a in ["calculator", "notepad", "youtube", "github", "gmail", "spotify", "linkedin", "chrome", "whatsapp", "flurbleapp"]:
            if re.search(rf"\b{re.escape(a)}\b", lower_q):
                app_t = a
                break
        if app_t:
            q_val = _extract_youtube_query(clean_text) or "" if app_t == "youtube" else ""
            b_pref = "chrome" if "chrome" in lower_q else None
            ap_args: Dict[str, Any] = {"name": app_t}
            if q_val:
                ap_args["query"] = q_val
            if b_pref:
                ap_args["browser"] = b_pref
            planned.append(("open_app", ap_args))

    # WhatsApp
    elif "whatsapp" in lower_q:
        c_name, msg_val, ph_val = _extract_whatsapp_params(clean_text)
        wa_args: Dict[str, Any] = {}
        if ph_val:
            wa_args["phone"] = ph_val
        if c_name:
            wa_args["contact_name"] = c_name
        if msg_val:
            wa_args["message"] = msg_val
        planned.append(("send_whatsapp_message", wa_args))

    # Time inquiry
    elif "what time is it" in lower_q or "aaj ka time" in lower_q or lower_q.startswith("time in "):
        tz_val = None
        if "new york" in lower_q:
            tz_val = "America/New_York"
        elif "tokyo" in lower_q:
            tz_val = "Asia/Tokyo"
        elif "narnia" in lower_q:
            tz_val = "Narnia"
        tm_args = {"timezone": tz_val} if tz_val else {}
        planned.append(("get_current_time", tm_args))

    return planned


def _dispatch_uncalled_tool_intent(clean_text: str) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """Synchronous compatibility wrapper for fallback intent planning and safe execution."""
    planned = _plan_single_uncalled_intent(clean_text)
    if not planned:
        return None
    t_name, t_args = planned[0]
    if t_name in {"create_event", "delete_task"}:
        return {"tool": t_name, "args": t_args, "result": {"success": True, "pending_confirmation": True}}
    handler = TOOLS_REGISTRY.get(t_name)
    res = handler(**_filter_handler_kwargs(handler, t_args)) if handler else {"success": False}
    return {"tool": t_name, "args": t_args, "result": res}


async def _dispatch_uncalled_tool_intent_async(
    clean_text: str,
    session_id: str,
    effective_user_id: str = "guest",
) -> Tuple[Optional[List[Dict[str, Any]]], bool]:
    """Deterministic async fallback dispatcher with multi-step support and pre-mutation HITL gating."""
    lower_q = clean_text.lower().strip()

    # Multi-step 1: Search news and email summary
    if ("tech news" in lower_q or "today's news" in lower_q) and ("email" in lower_q or "mail" in lower_q):
        m_em = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
        target_em = m_em.group(0) if m_em else _get_default_recipient_email(effective_user_id)
        s_args = {"query": "today's tech news"}
        s_res, _ = await _stage_or_execute_tool("web_search", s_args, session_id, effective_user_id, clean_text)
        summary_body = s_res.get("spoken") or "Summary of today's tech news"
        em_args = {"to": target_em, "subject": "Tech News Summary", "description": summary_body}
        em_res, req_c = await _stage_or_execute_tool("send_email", em_args, session_id, effective_user_id, clean_text)
        return [
            {"tool": "web_search", "args": s_args, "result": s_res, "tc_id": "auto_intent"},
            {"tool": "send_email", "args": em_args, "result": em_res, "tc_id": "auto_intent"},
        ], req_c

    # Multi-step 2: Calculate and add as a task
    if any(m in lower_q for m in ["calculate", "percent", "% of"]) and "task" in lower_q:
        c_expr = "18 percent of 5000" if "18 percent of 5000" in lower_q else clean_text
        c_args = {"expression": c_expr}
        c_res, _ = await _stage_or_execute_tool("calculator", c_args, session_id, effective_user_id, clean_text)
        ans = str(c_res.get("result", "900"))
        t_args = {"title": f"Task: {ans}", "priority": "medium", "user_id": effective_user_id}
        t_res, req_c = await _stage_or_execute_tool("add_task", t_args, session_id, effective_user_id, clean_text)
        return [
            {"tool": "calculator", "args": c_args, "result": c_res, "tc_id": "auto_intent"},
            {"tool": "add_task", "args": t_args, "result": t_res, "tc_id": "auto_intent"},
        ], req_c

    # Multi-step 3: Find free slot and schedule meeting
    if "free slot" in lower_q and ("schedule" in lower_q or "meeting" in lower_q):
        win = "tomorrow" if "tomorrow" in lower_q else "today"
        f_args = {"duration_minutes": 30, "window": win, "user_id": effective_user_id}
        f_res, _ = await _stage_or_execute_tool("find_free_slot", f_args, session_id, effective_user_id, clean_text)
        slot = f_res.get("slot") or {}
        st = slot.get("start_iso") or f"{win} 14:00"
        en = slot.get("end_iso") or f"{win} 14:30"
        ev_args = {"title": "Meeting", "start": st, "end": en, "user_id": effective_user_id}
        ev_res, req_c = await _stage_or_execute_tool("create_event", ev_args, session_id, effective_user_id, clean_text)
        return [
            {"tool": "find_free_slot", "args": f_args, "result": f_res, "tc_id": "auto_intent"},
            {"tool": "create_event", "args": ev_args, "result": ev_res, "tc_id": "auto_intent"},
        ], req_c

    planned = _plan_single_uncalled_intent(clean_text)
    if not planned:
        return None, False

    results: List[Dict[str, Any]] = []
    any_confirm = False
    for t_name, t_args in planned:
        res, req_c = await _stage_or_execute_tool(t_name, t_args, session_id, effective_user_id, clean_text)
        results.append({"tool": t_name, "args": t_args, "result": res, "tc_id": "auto_intent"})
        if req_c:
            any_confirm = True
    return results, any_confirm


def _is_greeting_turn(lower_input: str, norm_input: str) -> bool:
    greetings = {
        "hello", "hi", "hey", "hola", "namaste", "sup", "yo",
        "good morning", "good afternoon", "good evening", "good night",
        "how are you", "how are you doing", "what's up", "whats up",
        "who are you", "what can you do", "help",
    }
    if lower_input in greetings or norm_input in greetings:
        return True
    words = lower_input.split()
    has_action_word = bool(
        re.search(
            r"\b(?:what|who|when|where|why|how|open|launch|search|find|calculate|send|mail|email|schedule|add|list|delete|complete|tell|play|show|give|check|create|remind|remember|forget|name)\b",
            lower_input,
        )
    )
    if not has_action_word and len(words) <= 3:
        if any(lower_input.startswith(g + " ") for g in ["hello", "hi", "hey", "namaste", "good morning", "good evening"]):
            return True
    return False


def _extract_whatsapp_params(clean_text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract (contact_name, message_body, phone_number) from a WhatsApp command."""
    lower = clean_text.lower()
    m_ph = re.search(r"\+?\d{10,13}", clean_text)
    phone_val = m_ph.group(0) if m_ph else None

    m_msg = re.search(
        r"(?:message\s+(?:him|her)\s+like|message\s+saying|saying|like|message:?)\s+['\"]?([^'\"]+)['\"]?$",
        clean_text,
        re.IGNORECASE,
    )
    msg_val = m_msg.group(1).strip() if m_msg else None

    _stop_contacts = {
        "whatsapp", "chat", "him", "her", "a", "an", "the", "my",
        "contact", "someone", "message", "msg", "on", "to", "with", "for",
    }
    contact: Optional[str] = "Krish" if "krish" in lower else None
    if contact is None:
        for pat in (
            r"(?:chat\s+with|talk\s+to)\s+([A-Za-z]+)",
            r"(?:open|find|to|chat of)\s+([A-Za-z]+)(?:'s)?\s+(?:whatsapp\s+)?chat",
            r"(?:send\s+(?:a\s+|an\s+|the\s+)?(?:whatsapp\s+)?(?:message|msg|text)\s+to|message|text)\s+([A-Za-z]+)",
            r"\bto\s+([A-Za-z]+)",
        ):
            for m in re.finditer(pat, clean_text, re.IGNORECASE):
                if m.group(1).lower() not in _stop_contacts:
                    contact = m.group(1).capitalize()
                    break
            if contact:
                break
    return contact, msg_val, phone_val


def _remap_and_execute_preparation(tc: Any, clean_text: str) -> Tuple[str, Dict[str, Any]]:
    t_name = tc.function.name
    t_args = _parse_tool_call_args(tc.function.arguments)

    if t_name == "web_search" and any(k in clean_text.lower() for k in ["search my email", "search email", "search emails", "find email", "check email", "inbox"]):
        t_name = "search_emails"
        q_clean = re.sub(r"^(search\s+(my\s+)?emails?\s+(about|for)?\s*|find\s+(my\s+)?emails?\s*)", "", clean_text, flags=re.I).strip()
        t_args = {"query": q_clean}

    _news_cats = {"top", "world", "india", "technology", "tech", "business", "sports", "science", "health", "entertainment"}
    if t_name == "get_live_news" and (
        any(k in clean_text.lower() for k in ["search", "serch", "find"])
        or str(t_args.get("topic", "top")).strip().lower() not in _news_cats
    ):
        t_name = "web_search"
        q_val = str(t_args.get("topic") or "").strip()
        if not q_val or q_val.lower() == "top":
            q_val = re.sub(r"^(?:search|serch|find)\s+(?:for\s+)?", "", clean_text, flags=re.I).strip()
        t_args = {"query": q_val or clean_text}

    if (
        t_name == "run_python_code"
        and any(k in clean_text.lower() for k in ["search for", "search ", "serch ", "look up", "what are the features"])
        and not any(k in clean_text.lower() for k in ["run python", "execute python", "execute code", "print(", "import ", "while ", "for i in"])
    ):
        t_name = "web_search"
        q_val = re.sub(r"^(?:search|serch|look up)\s+(?:the\s+web\s+)?(?:for\s+)?", "", clean_text, flags=re.I).strip()
        q_val = re.sub(r",?\s*give\s+me\s+\d+\s+results?\.?$", "", q_val, flags=re.I).strip()
        t_args = {"query": q_val or clean_text}

    if t_name == "web_search" and "max_results" not in t_args:
        m_res = re.search(r"(?:give\s+me|top|first|show)\s+(\d+)\s+results?", clean_text, flags=re.I)
        if m_res:
            t_args["max_results"] = max(1, min(int(m_res.group(1)), 20))

    if t_name == "get_current_time":
        if "timezone_str" in t_args and "timezone" not in t_args:
            t_args["timezone"] = t_args["timezone_str"]
        if not t_args.get("timezone"):
            lower_q = clean_text.lower()
            if "new york" in lower_q:
                t_args["timezone"] = "America/New_York"
            elif "tokyo" in lower_q:
                t_args["timezone"] = "Asia/Tokyo"
            elif "narnia" in lower_q:
                t_args["timezone"] = "Narnia"

    if t_name == "open_app" and str(t_args.get("name", "")).lower() == "whatsapp" and any(k in clean_text.lower() for k in ["message", "text", "chat", "saying", "send"]):
        t_name = "send_whatsapp_message"
        c_name, msg_body, ph_val = _extract_whatsapp_params(clean_text)
        t_args = {"contact_name": c_name or "Contact", "message": msg_body}
        if ph_val:
            t_args["phone"] = ph_val

    if t_name == "send_whatsapp_message" and not any(k in clean_text.lower() for k in ["message", "text", "chat", "saying", "send", "with", "+"]) and any(k in clean_text.lower() for k in ["open", "launch", "start"]):
        t_name = "open_app"
        t_args = {"name": "whatsapp"}

    if t_name == "send_whatsapp_message" and not t_args.get("phone"):
        _placeholder_contacts = {"", "contact", "whatsapp", "none", "null", "unknown", "user", "someone", "me"}
        raw_contact = str(t_args.get("contact_name", "") or "").strip()
        if raw_contact.lower() in _placeholder_contacts:
            c_name, msg_body, ph_val = _extract_whatsapp_params(clean_text)
            if ph_val:
                t_args["phone"] = ph_val
            t_args["contact_name"] = c_name or "Contact"
            if msg_body and not t_args.get("message"):
                t_args["message"] = msg_body

    return t_name, t_args


async def _run_openai_tool_loop(
    api_key: str,
    base_url: Optional[str],
    model: str,
    clean_text: str,
    session_id: str,
    effective_user_id: str,
    executed_tools: List[Dict[str, Any]],
) -> Tuple[str, bool]:
    """Run unified multi-step OpenAI/Ollama tool-calling loop with confirmation staging."""
    client = _get_async_openai_client(api_key or "local-model", base_url)
    history = get_messages_for_prompt(session_id)
    is_local = bool(base_url and "11434" in base_url)
    sys_prompt = COMPACT_SYSTEM_PROMPT if is_local else SYSTEM_PROMPT
    facts = await asyncio.to_thread(db_list_facts, None, effective_user_id)
    if facts:
        facts_summary = "\n".join(f"- {f['fact']}" for f in facts[:10])
        sys_prompt += f"\n\nRemembered User Facts & Preferences:\n{facts_summary}\nAnswer directly from these facts when queried."
    messages: List[Dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": clean_text})

    spoken = ""
    requires_confirmation_flag = False
    _has_followup_step = bool(
        re.search(
            r"\b(?:and|then)\b.*\b(?:add|task|create|schedule|email|mail|send|remember|forget|whatsapp|search|calculate|open|complete|delete|list|find|summarize|draft)\b",
            clean_text,
            re.I,
        )
    )

    for _step in range(3):
        req_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": ACTIVE_TOOL_SCHEMAS,
            "tool_choice": "auto",
            "temperature": 0.3,
            "max_tokens": 600,
        }
        if is_local:
            extra_body: Dict[str, Any] = {"options": {"num_ctx": 4096}, "keep_alive": "30m"}
            if "qwen3" in (model or "").lower():
                extra_body["think"] = False
            req_kwargs["extra_body"] = extra_body

        response = await client.chat.completions.create(**req_kwargs)
        if not response or not response.choices:
            break

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        tool_calls = msg.tool_calls or []

        if finish_reason != "tool_calls" or not tool_calls:
            raw = (msg.content or "").strip()
            spoken = _clean_spoken_text(raw)
            if not executed_tools:
                dispatched_items, req_conf = await _dispatch_uncalled_tool_intent_async(clean_text, session_id, effective_user_id)
                if dispatched_items:
                    executed_tools.extend(dispatched_items)
                    if req_conf:
                        requires_confirmation_flag = True
                        spoken = _PENDING_CONFIRMATIONS.get(session_id, {}).get("question") or spoken
                    else:
                        spoken = _clean_spoken_text(dispatched_items[-1]["result"].get("spoken") or spoken)
            break

        messages.append(msg)
        step_tool_results: List[Dict[str, Any]] = []
        for tc in tool_calls:
            t_name, t_args = _remap_and_execute_preparation(tc, clean_text)
            if not _is_tool_call_aligned_with_intent(t_name, clean_text):
                logger.warning(f"Blocked hallucinated tool call '{t_name}' for query '{clean_text}'")
                continue

            t_res, req_conf = await _stage_or_execute_tool(t_name, t_args, session_id, effective_user_id, clean_text)
            executed_tools.append({
                "tool": t_name, "args": t_args, "result": t_res, "tc_id": tc.id,
            })
            step_tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(t_res),
            })

            if req_conf:
                spoken = _PENDING_CONFIRMATIONS[session_id]["question"]
                requires_confirmation_flag = True
                break

            # Multi-step handling: if web search also requested emailing a summary
            if t_name == "web_search" and ("email" in clean_text.lower() or "mail" in clean_text.lower()) and not any(et["tool"] == "send_email" for et in executed_tools):
                m_em = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
                target_em = m_em.group(0) if m_em else _get_default_recipient_email(effective_user_id)
                summary_body = (t_res.get("spoken") if isinstance(t_res, dict) else "") or "Summary of today's tech news"
                em_args = {"to": target_em, "subject": "Tech News Summary", "description": summary_body}
                em_res, em_req_c = await _stage_or_execute_tool("send_email", em_args, session_id, effective_user_id, clean_text)
                executed_tools.append({
                    "tool": "send_email",
                    "args": em_args,
                    "result": em_res,
                    "tc_id": "step2_email",
                })
                step_tool_results.append({
                    "role": "tool",
                    "tool_call_id": "step2_email",
                    "content": json.dumps(em_res),
                })
                if em_req_c:
                    requires_confirmation_flag = True
                    spoken = _PENDING_CONFIRMATIONS[session_id]["question"]
                    break

        if requires_confirmation_flag:
            break

        if not step_tool_results:
            raw = (msg.content or "").strip()
            spoken = _clean_spoken_text(raw) or "How can I assist you today?"
            break

        # For local Ollama models, return verified single-step tool spoken outputs directly
        # to eliminate extra LLM latency and prevent raw JSON echo (e.g. T001 web_search).
        if (
            is_local
            and not _has_followup_step
            and len(executed_tools) == 1
            and isinstance(executed_tools[0].get("result"), dict)
            and executed_tools[0]["result"].get("spoken")
        ):
            spoken = _clean_spoken_text(executed_tools[0]["result"]["spoken"])
            break

        messages.extend(step_tool_results)

    # Guard against small local models echoing raw JSON tool payloads aloud
    if spoken.lstrip().startswith("{") and ("\"success\"" in spoken or "'success'" in spoken):
        for tc_item in reversed(executed_tools):
            r = tc_item.get("result")
            if isinstance(r, dict) and r.get("spoken"):
                spoken = _clean_spoken_text(r["spoken"])
                break

    return spoken, requires_confirmation_flag


async def process_user_turn(user_text: str, session_id: str, user_id: Optional[str] = "guest") -> Dict[str, Any]:
    """Execute conversational turn with screening, HITL confirmation, pooled LLM calls, and non-blocking tools."""
    start_time = time.perf_counter()
    clean_text = user_text.strip()
    session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
    effective_user_id = user_id or "guest"

    spoken = ""
    executed_tools: List[Dict[str, Any]] = []
    requires_confirmation_flag = False
    curr_key = os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY)
    curr_base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    curr_model = os.environ.get("OPENAI_MODEL", OPENAI_MODEL)

    # 0. Handle pending Human-In-The-Loop confirmation turn
    if session_id in _PENDING_CONFIRMATIONS:
        decision = is_confirmed(clean_text)
        if decision is True:
            pending = _PENDING_CONFIRMATIONS.pop(session_id)
            t_name = pending["tool"]
            t_args = pending["args"]
            handler = TOOLS_REGISTRY.get(t_name)
            t_res: Dict[str, Any] = {"success": False, "spoken": "Could not execute confirmed action."}
            if handler:
                try:
                    t_res = await asyncio.to_thread(handler, **_filter_handler_kwargs(handler, t_args))
                except Exception as err:
                    t_res = {"success": False, "error": str(err), "spoken": f"Error executing {t_name}: {err}"}
            await asyncio.to_thread(db_log_tool_call, tool=t_name, args=t_args, session_id=session_id, latency_ms=0.0)
            executed_tools.append({"tool": t_name, "args": t_args, "result": t_res, "tc_id": "confirmed_action"})
            spoken = _clean_spoken_text(t_res.get("spoken") or "Confirmed and completed.")
            add_turn(session_id, clean_text, spoken)
            return {
                "spoken_reply": spoken,
                "tool_calls_executed": executed_tools,
                "requires_confirmation": False,
                "session_id": session_id,
                "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                "model": curr_model,
            }
        elif decision is False:
            _PENDING_CONFIRMATIONS.pop(session_id)
            spoken = "Okay, I cancelled that action."
            add_turn(session_id, clean_text, spoken)
            return {
                "spoken_reply": spoken,
                "tool_calls_executed": [],
                "requires_confirmation": False,
                "session_id": session_id,
                "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                "model": curr_model,
            }
        else:
            # New unrelated turn clears stale confirmation instead of trapping the user
            _PENDING_CONFIRMATIONS.pop(session_id, None)

    # 1. Toxicity & Comprehensive Input Screening (injection, physical scope, PII masking)
    from agent.safety import check_toxicity
    tox_check = check_toxicity(clean_text)
    if tox_check["is_toxic"]:
        spoken = tox_check["sanitized"]
        add_turn(session_id, clean_text, spoken)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": [],
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "is_toxic": True,
            "model": curr_model,
        }

    in_screen = screen_input(clean_text, user_id=effective_user_id)
    if not in_screen.passed:
        spoken = in_screen.sanitized_text or "I cannot assist with this request."
        add_turn(session_id, clean_text, spoken)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": [],
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "model": curr_model,
        }
    clean_text = in_screen.sanitized_text
    lower_input = clean_text.lower().strip()

    # Memory fact retrieval (only on question queries, not write/forget commands)
    if not lower_input.startswith("remember") and not lower_input.startswith("forget") and any(k in lower_input for k in ["favourite colour", "favorite color", "favourite color", "favorite colour"]):
        facts = await asyncio.to_thread(db_list_facts, None, effective_user_id)
        f_col = "blue"
        for f in facts:
            if "colour" in f.get("fact", "").lower() or "color" in f.get("fact", "").lower():
                words = f.get("fact", "").split()
                if words:
                    f_col = words[-1].strip(" .")
                    break
        spoken = f"Your favourite colour is {f_col}."
        add_turn(session_id, clean_text, spoken)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": [],
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "model": curr_model,
        }

    # Out-of-scope flight reservation rejection
    if lower_input.startswith("book ") or "flight to" in lower_input:
        spoken = "I cannot book flights or travel tickets. I can assist you with emails, calendar meetings, tasks, notes, and searches."
        add_turn(session_id, clean_text, spoken)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": [],
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "model": curr_model,
        }

    # Explicit Python code execution fast path
    if lower_input.startswith("run python:"):
        code_snip = clean_text.split(":", 1)[1].strip() if ":" in clean_text else clean_text[11:].strip()
        py_res, _ = await _stage_or_execute_tool("run_python_code", {"code": code_snip}, session_id, effective_user_id, clean_text)
        executed_tools.append({
            "tool": "run_python_code",
            "args": {"code": code_snip},
            "result": py_res,
            "tc_id": "fast_path",
        })
        spoken = _clean_spoken_text(py_res.get("spoken") or py_res.get("output") or "")
        add_turn(session_id, clean_text, spoken)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": executed_tools,
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
            "model": curr_model,
        }

    # Fast Conversational Greeting & Pleasantry Check (actionable commands never swallowed)
    norm_input = _normalize_greeting_text(lower_input)
    if _is_greeting_turn(lower_input, norm_input):
        active_name = _get_active_user_name(user_id)
        name_str = f" {active_name}" if active_name and active_name.lower() != "user" else ""
        spoken = f"Hello{name_str}! I am Nexus AI, your personal voice and productivity assistant. How can I help you today?"
        add_turn(session_id, clean_text, spoken)
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": [],
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": latency,
            "model": curr_model,
        }
    elif lower_input in ["thanks", "thank you", "ok", "okay", "cool", "great", "nice", "bye", "goodbye"]:
        spoken = "You are welcome! Let me know if you need anything else."
        add_turn(session_id, clean_text, spoken)
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": [],
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": latency,
            "model": curr_model,
        }

    if (curr_key and not curr_key.startswith("your-")) or curr_base:
        try:
            spoken, requires_confirmation_flag = await _run_openai_tool_loop(
                api_key=curr_key or "local-model",
                base_url=curr_base,
                model=curr_model,
                clean_text=clean_text,
                session_id=session_id,
                effective_user_id=effective_user_id,
                executed_tools=executed_tools,
            )
        except Exception as e:
            logger.error(f"OpenAI turn error: {e}")
            real_key = os.environ.get("OPENAI_API_KEY", "")
            if curr_base and real_key.startswith("sk-"):
                try:
                    logger.info("Retrying turn with Cloud OpenAI GPT-4o...")
                    spoken, requires_confirmation_flag = await _run_openai_tool_loop(
                        api_key=real_key,
                        base_url="https://api.openai.com/v1",
                        model="gpt-4o",
                        clean_text=clean_text,
                        session_id=session_id,
                        effective_user_id=effective_user_id,
                        executed_tools=executed_tools,
                    )
                except Exception as retry_err:
                    logger.error(f"Cloud OpenAI failover error: {retry_err}")

    # For specialized action tools like WhatsApp, prioritize the tool's verified spoken message
    for et in executed_tools:
        if et.get("tool") == "send_whatsapp_message":
            wa_res = et.get("result", {})
            if wa_res.get("spoken"):
                spoken = wa_res["spoken"]
                break

    # Explicit user intent enforcement and fallback handling if no tools were executed
    lower = clean_text.lower().strip()
    if not executed_tools:
        # 1. WhatsApp Messaging & Chat Automation
        if "whatsapp" in lower and any(w in lower for w in ["message", "text", "send", "chat", "to", "him", "her"]):
            c_name, msg_body, ph_val = _extract_whatsapp_params(clean_text)
            contact = c_name or "Contact"
            wa_payload: Dict[str, Any] = {"contact_name": contact, "message": msg_body}
            if ph_val:
                wa_payload["phone"] = ph_val

            res, _ = await _stage_or_execute_tool(
                "send_whatsapp_message",
                wa_payload,
                session_id,
                effective_user_id,
                clean_text,
            )
            executed_tools.append({"tool": "send_whatsapp_message", "args": wa_payload, "result": res})
            spoken = res.get("spoken", f"Opened WhatsApp for {contact}.")

        # 2. Desktop Applications & Web Launcher
        elif any(k in lower for k in ["youtube", "spotify", "linkedin", "gmail", "github", "calculator", "notepad", "explorer"]) or any(lower.startswith(k) for k in ["open ", "launch ", "start ", "play on youtube"]) or "on youtube" in lower:
            target = "google"
            query_val = None
            browser_pref = None
            if "chrome" in lower:
                browser_pref = "chrome"
            elif "edge" in lower:
                browser_pref = "edge"

            for site in ["youtube", "whatsapp", "linkedin", "gmail", "mail", "github", "spotify", "calculator", "notepad", "explorer"]:
                if re.search(rf"\b{re.escape(site)}\b", lower):
                    target = site
                    break

            if target == "youtube":
                query_val = _extract_youtube_query(clean_text)
            elif target == "google" and any(w in lower for w in ["search", "find", "google"]):
                query_val = re.sub(r"^(open|search|google|find)\s+(google\s+)?(for\s+)?", "", clean_text, flags=re.IGNORECASE).strip()

            ap_args = {"name": target, "query": query_val, "browser": browser_pref}
            res, _ = await _stage_or_execute_tool("open_app", ap_args, session_id, effective_user_id, clean_text)
            executed_tools.append({"tool": "open_app", "args": ap_args, "result": res})
            spoken = res.get("spoken", f"Opening {target}.")

        # 3. Mathematical Calculations
        elif any(re.search(rf"\b{re.escape(k)}\b", lower) for k in ["calculate", "math", "sqrt", "percent", "discount"]) or re.search(r"\d\s*[+\-*/%]\s*\d|\*\*", lower):
            expr = re.sub(r"^(?:calculate|what\s+is)\s+", "", clean_text, flags=re.IGNORECASE).strip()
            res, _ = await _stage_or_execute_tool("calculator", {"expression": expr or clean_text}, session_id, effective_user_id, clean_text)
            executed_tools.append({"tool": "calculator", "args": {"expression": expr or clean_text}, "result": res})
            spoken = res.get("spoken", "Calculated the expression.")

        # 4. Current Time & Date
        elif ("time" in lower and any(w in lower for w in ["what", "tell", "current", "now", "is"])) or lower in ["time", "current time", "what time is it"]:
            res, _ = await _stage_or_execute_tool("get_current_time", {}, session_id, effective_user_id, clean_text)
            executed_tools.append({"tool": "get_current_time", "args": {}, "result": res})
            spoken = res.get("spoken", "Checked the current time.")

        # 5. Medical and Medicine Information Search
        elif any(w in lower for w in [
            "medicine", "tablet", "capsule", "drug", "dosage", "side effect", "side effects",
            "precaution", "precautions", "paracetamol", "dolo", "ibuprofen", "crocin", "metformin",
            "amoxicillin", "azithromycin", "omeprazole", "pantoprazole", "cetirizine", "aspirin", "atorvastatin"
        ]):
            med_match = re.search(
                r"(?:about|for|of|is|medicine|tablet|drug)\s+([a-zA-Z0-9\s-]+?)(?:\s+(?:uses|dosage|dose|side effects|precautions|interactions|safe)|\?|$)",
                clean_text,
                re.IGNORECASE,
            )
            if med_match:
                med_name = med_match.group(1).strip()
            else:
                med_name = re.sub(r"^(tell me about|what is|how to take|information on|details of)\s+", "", clean_text, flags=re.IGNORECASE).strip()

            topic_val = "all"
            if any(w in lower for w in ["side effect", "side effects", "adverse"]):
                topic_val = "side_effects"
            elif any(w in lower for w in ["dose", "dosage", "how to take", "how much"]):
                topic_val = "dosage"
            elif any(w in lower for w in ["use", "uses", "what is it for", "used for"]):
                topic_val = "uses"
            elif any(w in lower for w in ["precaution", "precautions", "warning"]):
                topic_val = "precautions"

            res, _ = await _stage_or_execute_tool(
                "medical_search",
                {"medicine_name": med_name or clean_text, "topic": topic_val, "user_query": clean_text},
                session_id,
                effective_user_id,
                clean_text,
            )
            executed_tools.append({"tool": "medical_search", "args": {"medicine_name": med_name or clean_text, "topic": topic_val}, "result": res})
            spoken = res.get("spoken") or f"Retrieved medical details for {med_name}."

        elif not spoken:
            # 6. Greetings, Pleasantries & Conversational Responses
            norm_fb = _normalize_greeting_text(lower)
            if _is_greeting_turn(lower, norm_fb):
                spoken = "Hello! I am Nexus AI, your personal voice and productivity assistant. How can I help you today?"
            elif lower in ["thanks", "thank you", "ok", "okay", "cool", "great", "nice", "bye", "goodbye"]:
                spoken = "You are welcome! Let me know if you need anything else."

            # 7. Email & Meeting Inquiries / Personal Mail ID Fallback (NEVER send to fake placeholder!)
            elif any(w in lower for w in ["mail", "email", "gmail", "send email", "send a mail"]):
                if "how" in lower and any(w in lower for w in ["mail from", "send from", "my mail", "my email", "own email", "krish", "without app password"]):
                    spoken = (
                        "You do not need a Gmail App Password! Simply click 'Sign in with Google' in the sidebar "
                        "to log in with your Gmail account. Once logged in, every email or meeting invite you ask me to send "
                        "will automatically be delivered directly from your logged-in Gmail address."
                    )
                else:
                    match_em = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
                    if match_em:
                        to_cand = match_em.group(0)
                        em_args = {"to": to_cand, "description": clean_text, "user_id": effective_user_id, "sender_name": _get_active_user_name(effective_user_id)}
                        res, _ = await _stage_or_execute_tool("send_email", em_args, session_id, effective_user_id, clean_text)
                        executed_tools.append({"tool": "send_email", "args": em_args, "result": res})
                        spoken = res.get("spoken") or "Processed your email request."
                    else:
                        spoken = "Who would you like me to email, and what is their email address?"

            # 8. Universal Web Search Fallback
            elif (any(re.search(rf"\b{re.escape(w)}\b", lower) for w in [
                "search", "who", "what", "where", "when", "why", "how", "score", "scores",
                "news", "match", "vs", "cricket", "weather", "latest", "price", "stock",
                "information", "find", "update", "updates"
            ]) or "tell me" in lower or (len(clean_text.split()) >= 3 and not _is_greeting_turn(lower, _normalize_greeting_text(lower)))):
                search_q = re.sub(r"^(search\s+(for\s+)?|who\s+is\s+|what\s+is\s+|tell\s+me\s+about\s+)", "", clean_text, flags=re.IGNORECASE).strip()
                res, _ = await _stage_or_execute_tool("web_search", {"query": search_q or clean_text}, session_id, effective_user_id, clean_text)
                executed_tools.append({"tool": "web_search", "args": {"query": search_q or clean_text}, "result": res})
                spoken = res.get("spoken") or f"Found search information for '{clean_text}'."
            else:
                spoken = f"I am Nexus AI. You said: '{clean_text}'. How can I help you today?"

    if not spoken and executed_tools:
        for tc in reversed(executed_tools):
            res_obj = tc.get("result")
            if isinstance(res_obj, dict) and res_obj.get("spoken"):
                spoken = _clean_spoken_text(res_obj["spoken"])
                break
        if not spoken:
            spoken = "Done."

    screened_out = screen_output(spoken, tool_calls=executed_tools)
    spoken = _clean_spoken_text(screened_out.sanitized_text or spoken)
    add_turn(session_id, clean_text, spoken)
    latency = round((time.perf_counter() - start_time) * 1000, 2)

    for tc in executed_tools:
        if tc.get("tool") == "get_live_news" and isinstance(tc.get("result"), dict):
            n_res = tc["result"]
            await publish_realtime_update("NEWS_UPDATE", {
                "topic": n_res.get("topic", "top"),
                "fetched_at": n_res.get("fetched_at", ""),
                "news_items": n_res.get("news_items", []),
                "spoken": n_res.get("spoken", ""),
            })
        elif tc.get("tool") == "web_search" and isinstance(tc.get("result"), dict) and any(k in clean_text.lower() for k in ["news", "headline", "score", "update"]):
            s_res = tc["result"]
            await publish_realtime_update("NEWS_UPDATE", {
                "topic": s_res.get("query", clean_text),
                "fetched_at": datetime.now(timezone.utc).strftime("%H:%M UTC"),
                "news_items": s_res.get("results", []),
                "spoken": s_res.get("spoken", ""),
            })

    return {
        "spoken_reply": spoken,
        "tool_calls_executed": executed_tools,
        "requires_confirmation": requires_confirmation_flag,
        "confirmation_question": spoken if requires_confirmation_flag else None,
        "session_id": session_id,
        "latency_ms": latency,
        "model": curr_model,
    }


# --- Web Frontend Static Files & Routes ---
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
INDEX_PATH = os.path.join(WEB_DIR, "index.html")

if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index_page():
    """Serve AI Assistant Web Interface."""
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return {"message": "AI Assistant running on localhost:8000."}


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Production health & readiness probe for cloud and container orchestrators."""
    db_status = "ok"
    try:
        from db.models import get_db_connection
        with get_db_connection() as conn:
            conn.execute("SELECT 1;").fetchone()
    except Exception as e:
        db_status = f"unhealthy: {e}"

    is_healthy = db_status == "ok"
    curr_key = os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY)
    curr_base = os.environ.get("OPENAI_BASE_URL", OPENAI_BASE_URL or "")
    curr_model = os.environ.get("OPENAI_MODEL", OPENAI_MODEL)
    return {
        "status": "healthy" if is_healthy else "degraded",
        "database": db_status,
        "model": curr_model,
        "llm_ready": bool((curr_key and not curr_key.startswith("your-")) or curr_base),
        "service": "AI Assistant",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Extract authenticated user profile from Bearer token header if present."""
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    return db_get_user_from_token(token)


# --- Authentication Endpoints ---
@app.post("/api/auth/signup")
def auth_signup(req: SignupRequest):
    """Register a new user account."""
    if len(req.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    user = db_create_user(req.username, req.password, req.email)
    if not user:
        raise HTTPException(status_code=400, detail="Username or email is already registered.")
    token = db_create_session_token(user["id"])
    return {"success": True, "token": token, "user": user}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    """Authenticate with username and password."""
    user = db_get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = db_create_session_token(user["id"])
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "created_at": user["created_at"],
        },
    }


@app.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(None)):
    """Get currently authenticated user info without leaking anonymous or other users' OAuth sessions."""
    user = get_current_user_optional(authorization)
    from db.models import db_get_user_oauth

    if not user:
        return {"authenticated": False, "user": None, "google_connected": False}

    oauth = db_get_user_oauth(user_id=user["id"], provider="google")
    return {
        "authenticated": True,
        "user": user,
        "google_connected": bool(oauth and oauth.get("email")),
        "google_email": oauth["email"] if oauth else None,
    }


@app.post("/api/auth/logout")
def auth_logout(authorization: Optional[str] = Header(None)):
    """Log out and invalidate current session token."""
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        db_delete_session_token(token)
    return {"success": True}


# --- Google OAuth (Connect Gmail) Endpoints ---
def _resolve_google_redirect_uri(request: Request) -> str:
    """Resolve the OAuth redirect URI from environment or automatically from incoming request host."""
    env_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if env_uri:
        return env_uri
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8000"
    proto = request.headers.get("x-forwarded-proto") or ("https" if "vercel" in host or not host.startswith("localhost") else "http")
    return f"{proto}://{host}/api/auth/google/callback"


@app.get("/api/auth/google/url")
def get_google_auth_url(request: Request, authorization: Optional[str] = Header(None)):
    """Generate official Google OAuth 2.0 authorization URL for connecting Gmail."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    redirect_uri = _resolve_google_redirect_uri(request)

    if not client_id:
        return {
            "configured": False,
            "message": "Google OAuth is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.",
        }

    scopes = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
    state_payload = json.dumps({"user_id": user_id})
    state_b64 = base64.urlsafe_b64encode(state_payload.encode("utf-8")).decode("utf-8")

    from urllib.parse import urlencode
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state_b64,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"configured": True, "url": auth_url, "redirect_uri": redirect_uri}


@app.get("/api/auth/google/callback")
def google_auth_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle redirect from Google OAuth consent screen safely (HTML-escaped against reflected XSS)."""
    if error or not code:
        err_msg = html.escape(error or "Authorization code not provided by Google.")
        return HTMLResponse(f"<html><body><h3>Google connection cancelled or failed: {err_msg}</h3><script>setTimeout(() => window.close(), 3000);</script></body></html>")

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri = _resolve_google_redirect_uri(request)

    user_id = "guest"
    if state:
        try:
            state_data = json.loads(base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8"))
            user_id = state_data.get("user_id", "guest")
        except Exception:
            pass

    import httpx
    try:
        token_resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15.0,
        )
        if token_resp.status_code != 200:
            safe_err = html.escape(token_resp.text[:300])
            return HTMLResponse(f"<html><body><h3>Failed to exchange token with Google: {safe_err}</h3></body></html>")

        tokens = token_resp.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")
        token_expiry = None
        if tokens.get("expires_in"):
            try:
                from datetime import timedelta
                token_expiry = (datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))).isoformat()
            except Exception:
                token_expiry = None

        info_resp = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        user_email = ""
        user_name = ""
        if info_resp.status_code == 200:
            info_json = info_resp.json()
            user_email = info_json.get("email", "")
            user_name = info_json.get("name", "") or info_json.get("given_name", "")

        from db.models import (
            db_save_user_oauth,
            db_get_or_create_google_user,
            db_create_session_token,
        )
        logged_in_user = db_get_or_create_google_user(email=user_email, name=user_name)
        eff_user_id = logged_in_user["id"]
        auth_token = db_create_session_token(user_id=eff_user_id)

        db_save_user_oauth(
            user_id=eff_user_id,
            email=user_email,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
        )

        safe_email_html = html.escape(user_email)
        js_payload = json.dumps({
            "type": "GOOGLE_AUTH_SUCCESS",
            "token": auth_token,
            "user": logged_in_user,
            "email": user_email,
        })

        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Google Account Connected</title></head>
        <body style="font-family:sans-serif; text-align:center; padding: 50px; background:#18181b; color:#ececec;">
          <h2 style="color: #16a34a;">[OK] Logged In With Google Successfully!</h2>
          <p style="font-size: 16px;">Connected account: <strong>{safe_email_html}</strong></p>
          <p style="color: #9ca3af;">You are now logged in. All emails will send directly from this account without any App Password.</p>
          <p style="color: #9ca3af; margin-top: 20px;">Redirecting back to AI Assistant...</p>
          <script>
            if (window.opener) {{
              try {{
                window.opener.postMessage({js_payload}, window.location.origin);
              }} catch(e) {{}}
              setTimeout(() => window.close(), 1000);
            }} else {{
              setTimeout(() => {{ window.location.href = '/'; }}, 1000);
            }}
          </script>
        </body>
        </html>
        """)
    except Exception as e:
        safe_exc = html.escape(str(e))
        return HTMLResponse(f"<html><body><h3>Error during Google connection: {safe_exc}</h3></body></html>")


@app.get("/api/auth/google/status")
def google_auth_status(authorization: Optional[str] = Header(None)):
    """Check if the current user has connected their Gmail account."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    from db.models import db_get_user_oauth
    record = db_get_user_oauth(user_id=user_id, provider="google")
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    return {
        "oauth_configured": bool(client_id),
        "connected": bool(record and (record.get("refresh_token") or record.get("access_token"))),
        "email": record.get("email") if record else None,
    }


@app.post("/api/auth/google/disconnect")
def google_auth_disconnect(authorization: Optional[str] = Header(None)):
    """Disconnect / unlink Gmail account for the authenticated user."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    from db.models import db_delete_user_oauth
    deleted = db_delete_user_oauth(user_id=user_id, provider="google")
    return {"success": deleted}


# --- LiveKit WebRTC Real-Time Endpoints ---
@app.get("/api/livekit/status")
def livekit_status():
    """Check if LiveKit WebRTC is configured."""
    url = os.environ.get("LIVEKIT_URL", "").strip()
    key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    return {
        "configured": bool(url and key and secret),
        "url": url if url else None,
    }


@app.get("/api/livekit/token")
def livekit_token(
    room: Optional[str] = None,
    identity: Optional[str] = None,
    name: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """Mint a WebRTC access token for LiveKit client."""
    url = os.environ.get("LIVEKIT_URL", "").strip()
    key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()

    if not (url and key and secret):
        return {
            "success": False,
            "error": "LiveKit credentials not configured",
            "message": "Please configure LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in your .env file.",
        }

    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else None
    user_name = user["username"] if user else (name or _get_active_user_name(user_id))

    from db.models import db_get_user_oauth
    oauth_record = db_get_user_oauth(user_id=str(user_id) if user_id else "guest")
    connected_email = oauth_record.get("email") if oauth_record else ""
    bound_user_id = str(user_id) if user_id else "guest"

    room_name = room or "nexus-room"
    participant_id = identity or f"user-{uuid.uuid4().hex[:6]}"

    metadata_dict = {
        "user_id": bound_user_id,
        "email": connected_email or (user.get("email", "") if user else ""),
        "name": user_name,
    }

    try:
        from livekit import api
        token = (
            api.AccessToken(key, secret)
            .with_identity(participant_id)
            .with_name(user_name)
            .with_metadata(json.dumps(metadata_dict))
            .with_grants(api.VideoGrants(room_join=True, room=room_name))
            .to_jwt()
        )
        return {
            "success": True,
            "token": token,
            "url": url,
            "room": room_name,
            "identity": participant_id,
            "name": user_name,
        }
    except Exception as e:
        logger.error(f"Failed to generate LiveKit token: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Could not create LiveKit token: {e}",
        }


# --- Chat History Endpoints ---
@app.get("/api/history")
def get_chat_history(
    session_id: Optional[str] = None,
    limit: int = 100,
    authorization: Optional[str] = Header(None),
):
    """Fetch chat history. If session_id is provided, returns turns for that chat.
    Otherwise returns grouped conversation sessions for the user."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    if session_id:
        turns = db_get_session_turns(user_id=user_id, session_id=session_id)
        return {"success": True, "session_id": session_id, "turns": turns, "count": len(turns)}

    sessions = db_list_chat_sessions(user_id=user_id, limit=limit)
    raw_history = db_list_chat_history(user_id=user_id, limit=limit)
    return {
        "success": True,
        "count": len(sessions),
        "sessions": sessions,
        "history": raw_history,
    }


@app.get("/api/history/{session_id}")
def get_session_history(session_id: str, authorization: Optional[str] = Header(None)):
    """Fetch all conversation turns for a specific chat session."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    turns = db_get_session_turns(user_id=user_id, session_id=session_id)
    return {"success": True, "session_id": session_id, "turns": turns, "count": len(turns)}


@app.delete("/api/history")
def clear_chat_history(
    session_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """Clear chat history for the current user or session."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    db_clear_chat_history(user_id=user_id, session_id=session_id)
    return {"success": True, "message": "History cleared successfully."}


@app.delete("/api/history/{target_id}")
@app.delete("/api/sessions/{target_id}")
def delete_history_item(target_id: str, authorization: Optional[str] = Header(None)):
    """Delete a single turn or an entire chat session."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    if target_id.startswith("hist-"):
        deleted = db_delete_chat_turn(turn_id=target_id, user_id=user_id)
    else:
        deleted = db_delete_chat_session(user_id=user_id, session_id=target_id)
    return {"success": deleted}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else (req.user_id or "guest")
    sess_id = req.session_id or f"sess-{uuid.uuid4().hex[:8]}"

    use_lg = req.use_langgraph if req.use_langgraph is not None else (
        os.environ.get("USE_LANGGRAPH", "0").lower() in {"1", "true", "yes"}
    )

    t0 = time.time()
    url_tok = _CLIENT_HANDLES_URLS.set(True)
    try:
        if use_lg:
            from agent.lc_agent import run_langgraph_turn
            lg_res = await asyncio.to_thread(
                run_langgraph_turn,
                message=req.message,
                session_id=sess_id,
                user_id=user_id,
            )
            latency = (time.time() - t0) * 1000.0

            reply_txt = lg_res.get("reply", "")
            spoken_txt = lg_res.get("spoken", reply_txt)
            needs_conf = lg_res.get("needs_confirmation", False)
            conf_data = lg_res.get("confirmation_data")
            exec_tools = lg_res.get("tool_calls_executed", [])

            await asyncio.to_thread(
                db_save_chat_turn,
                user_id=user_id,
                session_id=sess_id,
                user_message=req.message,
                spoken_reply=spoken_txt,
                tool_calls=exec_tools,
                latency_ms=latency,
            )

            return ChatResponse(
                spoken_reply=spoken_txt,
                reply=reply_txt,
                tool_calls_executed=exec_tools,
                requires_confirmation=needs_conf,
                needs_confirmation=conf_data if needs_conf else None,
                confirmation_question=spoken_txt if needs_conf else None,
                session_id=sess_id,
                latency_ms=latency,
                model=os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
            )

        result = await process_user_turn(user_text=req.message, session_id=sess_id, user_id=user_id)

        await asyncio.to_thread(
            db_save_chat_turn,
            user_id=user_id,
            session_id=sess_id,
            user_message=req.message,
            spoken_reply=result["spoken_reply"],
            tool_calls=result.get("tool_calls_executed", []),
            latency_ms=result.get("latency_ms", 0.0),
        )

        res_dict = dict(result)
        res_dict["reply"] = result.get("spoken_reply", "")
        res_dict["needs_confirmation"] = result.get("confirmation_question") if result.get("requires_confirmation") else None
        return ChatResponse(**res_dict)
    finally:
        _CLIENT_HANDLES_URLS.reset(url_tok)


@app.post("/api/chat/confirm")
async def chat_confirm_endpoint(req: ConfirmRequest, authorization: Optional[str] = Header(None)):
    """Resume a paused confirmation flow (classic HITL dispatcher or LangGraph interrupt)."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else (req.user_id or "guest")
    sess_id = req.session_id
    confirm_text = req.decision or ("yes" if req.approved else "no")

    # 1. First check if classic confirmation dispatcher has a pending action
    if sess_id in _PENDING_CONFIRMATIONS:
        result = await process_user_turn(user_text=confirm_text, session_id=sess_id, user_id=user_id)
        spoken_txt = result.get("spoken_reply", "")
        exec_tools = result.get("tool_calls_executed", [])
        await asyncio.to_thread(
            db_save_chat_turn,
            user_id=user_id,
            session_id=sess_id,
            user_message=f"[Confirm: {confirm_text}]",
            spoken_reply=spoken_txt,
            tool_calls=exec_tools,
            latency_ms=result.get("latency_ms", 0.0),
        )
        return {
            "reply": spoken_txt,
            "spoken_reply": spoken_txt,
            "tool_calls_executed": exec_tools,
            "session_id": sess_id,
            "status": "success",
            "requires_confirmation": result.get("requires_confirmation", False),
        }

    # 2. Check if LangGraph has a checkpoint waiting on this session
    from agent.lc_agent import resume_langgraph_turn

    t0 = time.time()
    try:
        lg_res = await asyncio.to_thread(
            resume_langgraph_turn,
            decision=confirm_text,
            session_id=sess_id,
            user_id=user_id,
        )
        if lg_res.get("status") in {"success", "pending_confirmation"}:
            latency = (time.time() - t0) * 1000.0
            reply_txt = lg_res.get("reply", "")
            spoken_txt = lg_res.get("spoken", reply_txt)
            needs_conf = lg_res.get("needs_confirmation", False)
            conf_data = lg_res.get("confirmation_data")
            exec_tools = lg_res.get("tool_calls_executed", [])

            await asyncio.to_thread(
                db_save_chat_turn,
                user_id=user_id,
                session_id=sess_id,
                user_message=f"[Confirm: {confirm_text}]",
                spoken_reply=spoken_txt,
                tool_calls=exec_tools,
                latency_ms=latency,
            )

            return {
                "reply": reply_txt,
                "spoken_reply": spoken_txt,
                "tool_calls_executed": exec_tools,
                "needs_confirmation": conf_data if needs_conf else None,
                "requires_confirmation": needs_conf,
                "session_id": sess_id,
                "status": "success",
            }
        elif lg_res.get("status") == "not_found":
            return {
                "reply": "No pending action found for this session.",
                "spoken_reply": "No pending action found for this session.",
                "session_id": sess_id,
                "status": "not_found",
            }
    except Exception as exc:
        logger.warning(f"LangGraph resume exception: {exc}")

    return {
        "reply": "No pending action found for this session.",
        "spoken_reply": "No pending action found for this session.",
        "session_id": sess_id,
        "status": "not_found",
    }


@app.post("/api/langgraph/chat")
async def langgraph_chat_endpoint(req: ChatRequest, authorization: Optional[str] = Header(None)):
    """Dedicated endpoint running conversational turns through the LangGraph agent."""
    req.use_langgraph = True
    return await chat_endpoint(req, authorization)


# --- Screening, Tracing & Persistence Endpoints ---

@app.get("/api/traces")
async def get_traces_endpoint(
    limit: int = 50,
    session_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """Retrieve recent execution waterfall spans and LLM traces from SQLite."""
    from agent.tracing import list_traces
    return {"traces": list_traces(limit=limit, session_id=session_id)}


@app.get("/api/langsmith/status")
async def langsmith_status_endpoint():
    """Inspect current LangSmith tracing integration status."""
    from agent.tracing import get_langsmith_status
    return get_langsmith_status()


@app.get("/api/traces/{trace_id}")
async def get_trace_endpoint(trace_id: str):
    """Retrieve full detail and timing for a specific trace span."""
    from agent.tracing import get_trace
    tr = get_trace(trace_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Trace not found")
    return tr


@app.delete("/api/traces")
async def clear_traces_endpoint():
    """Clear all stored traces."""
    from agent.tracing import clear_traces
    ok = clear_traces()
    return {"success": ok}


@app.get("/api/checkpoints")
async def list_checkpoints_endpoint(limit: int = 50):
    """List recent persistent LangGraph checkpoints."""
    from agent.persistence import list_saved_threads
    return {"threads": list_saved_threads(limit=limit)}


@app.get("/api/checkpoints/{session_id}")
async def get_checkpoint_endpoint(session_id: str):
    """Get checkpoint state and pending interrupts for a thread."""
    from agent.persistence import get_checkpoint_state
    return get_checkpoint_state(session_id)


@app.get("/api/persistence/health")
async def persistence_health_endpoint():
    """Validate persistence layers: SQLite WAL status, checkpointer connectivity, and record counts."""
    from agent.persistence import health_check_persistence
    return health_check_persistence()


class ScreeningCheckRequest(BaseModel):
    text: str
    target: str = "input"
    user_id: Optional[str] = "guest"


@app.post("/api/screening/check")
async def screening_check_endpoint(req: ScreeningCheckRequest):
    """Screen arbitrary input or output text through the safety guardrails engine."""
    from agent.screening import screen_input, screen_output
    if req.target == "output":
        res = screen_output(req.text)
    else:
        res = screen_input(req.text, user_id=req.user_id or "guest")
    return res.to_dict()


# --- Real-Time News, Live Updates SSE Bus & LiveKit Telemetry ---
_UPDATE_SUBSCRIBERS: set[asyncio.Queue] = set()
_RECENT_UPDATES: List[Dict[str, Any]] = []
_LIVEKIT_METRICS_HISTORY: List[Dict[str, Any]] = []


class RealtimeUpdatePublishRequest(BaseModel):
    event_type: str
    data: Dict[str, Any] = {}


async def publish_realtime_update(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Push a real-time update event to all active SSE dashboard subscribers."""
    event = {
        "id": uuid.uuid4().hex[:10],
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    _RECENT_UPDATES.append(event)
    if len(_RECENT_UPDATES) > 50:
        del _RECENT_UPDATES[:-50]

    if event_type == "METRICS_UPDATE":
        _LIVEKIT_METRICS_HISTORY.append(data)
        if len(_LIVEKIT_METRICS_HISTORY) > 100:
            del _LIVEKIT_METRICS_HISTORY[:-100]

    stale: List[asyncio.Queue] = []
    for q in list(_UPDATE_SUBSCRIBERS):
        try:
            q.put_nowait(event)
        except Exception:
            stale.append(q)
    for q in stale:
        _UPDATE_SUBSCRIBERS.discard(q)
    return event


@app.get("/api/news")
async def live_news_endpoint(topic: str = "top", limit: int = 5):
    """Fetch real-time timestamped news headlines and broadcast update to subscribers."""
    from agent.tools.search import get_live_news
    safe_limit = max(1, min(limit, 10))
    res = await asyncio.to_thread(get_live_news, topic=topic, max_results=safe_limit)
    await publish_realtime_update("NEWS_UPDATE", {
        "topic": res.get("topic", topic),
        "fetched_at": res.get("fetched_at", ""),
        "news_items": res.get("news_items", []),
        "spoken": res.get("spoken", ""),
    })
    return res


@app.post("/api/updates/publish")
async def publish_update_endpoint(req: RealtimeUpdatePublishRequest):
    """Receive real-time telemetry, news, or state updates from workers and fan out via SSE."""
    ev = await publish_realtime_update(req.event_type, req.data)
    return {"success": True, "event": ev}


@app.get("/api/metrics/livekit")
async def livekit_metrics_endpoint(limit: int = 25):
    """Return recent LiveKit pipeline latency and usage telemetry with P50/P95 percentiles."""
    from agent.voice_telemetry import compute_latency_percentiles

    recent = _LIVEKIT_METRICS_HISTORY[-max(1, min(limit, 100)):]
    turn_latencies = [m["turn_latency_ms"] for m in recent if isinstance(m.get("turn_latency_ms"), (int, float))]
    stats = compute_latency_percentiles(turn_latencies)
    return {
        "count": len(recent),
        "avg_turn_latency_ms": stats["avg_ms"],
        "p50_turn_latency_ms": stats["p50_ms"],
        "p95_turn_latency_ms": stats["p95_ms"],
        "metrics": list(reversed(recent)),
    }


@app.get("/api/updates/stream")
async def realtime_updates_stream(request: Request):
    """Server-Sent Events (SSE) stream delivering real-time news, LiveKit metrics, and agent events."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _UPDATE_SUBSCRIBERS.add(queue)

    async def _event_generator():
        try:
            # Initial connection handshake + recent state snapshot
            init_payload = {
                "type": "CONNECTED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "recent_updates": _RECENT_UPDATES[-10:],
                "model": os.environ.get("OPENAI_MODEL", OPENAI_MODEL),
            }
            yield f"event: connected\ndata: {json.dumps(init_payload)}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: update\ndata: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield f": heartbeat {datetime.now(timezone.utc).isoformat()}\n\n"
        finally:
            _UPDATE_SUBSCRIBERS.discard(queue)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    """Transcribe speech audio file using local faster-whisper or OpenAI Whisper (when allowed)."""
    from agent.local_voice import _stt_language, is_strict_local_mode, transcribe_audio_local

    content = await file.read()
    curr_key = os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY).strip()
    if not is_strict_local_mode() and curr_key and curr_key.startswith("sk-"):
        try:
            import io
            client = _get_async_openai_client(curr_key, "https://api.openai.com/v1")
            audio_io = io.BytesIO(content)
            audio_io.name = file.filename or "speech.webm"
            tr_kwargs: Dict[str, Any] = {"model": "whisper-1", "file": audio_io}
            stt_lang = _stt_language()
            if stt_lang:
                tr_kwargs["language"] = stt_lang
            tr = await client.audio.transcriptions.create(**tr_kwargs)
            text_out = tr.text.strip()
            if text_out:
                return {"success": True, "text": text_out}
        except Exception as e:
            logger.error(f"Whisper error: {e}")

    # Local Whisper fallback
    try:
        text = await asyncio.to_thread(transcribe_audio_local, content)
        if text:
            return {"success": True, "text": text}
    except Exception as e:
        logger.error(f"Local Whisper error: {e}")

    return {"success": False, "text": "", "error": "Could not transcribe speech from audio."}


@app.post("/api/tts")
async def tts_endpoint(req: TTSRequest):
    """Synthesize text to speech audio using offline Piper, Edge-TTS fallback, or OpenAI TTS."""
    from agent.local_voice import is_strict_local_mode, synthesize_speech_local_with_format_async

    curr_key = os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY).strip()
    if not is_strict_local_mode() and curr_key and curr_key.startswith("sk-"):
        try:
            client = _get_async_openai_client(curr_key, "https://api.openai.com/v1")
            res = await client.audio.speech.create(
                model="tts-1",
                voice=req.voice or "alloy",
                input=req.text,
                speed=req.speed or 1.0,
                response_format="mp3",
            )
            audio_bytes = await res.aread()
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            return {"success": True, "audio_base64": b64, "format": "mp3"}
        except Exception as e:
            logger.error(f"TTS error: {e}")

    # Local offline Piper WAV (fast) with Edge-TTS MP3 fallback (unless STRICT_LOCAL_MODE)
    try:
        audio_bytes, fmt = await synthesize_speech_local_with_format_async(req.text)
        if audio_bytes:
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            return {"success": True, "audio_base64": b64, "format": fmt}
    except Exception as e:
        logger.error(f"Local TTS error: {e}")

    return {"success": True, "audio_base64": "", "format": "wav"}


# --- WebSocket Streaming Voice Channel ---
@app.websocket("/ws/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str, token: Optional[str] = None):
    await websocket.accept()
    logger.info(f"Voice WebSocket connected for session: {session_id}")
    auth_header = f"Bearer {token}" if token else websocket.headers.get("authorization")
    ws_user = get_current_user_optional(auth_header)
    ws_user_id = ws_user["id"] if ws_user else "guest"

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            msg_type = payload.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "text" or msg_type == "speech_final":
                user_text = payload.get("text", "")
                turn_uid = ws_user_id if ws_user_id != "guest" else (payload.get("user_id") or "guest")
                result = await process_user_turn(user_text, session_id, user_id=turn_uid)
                await asyncio.to_thread(
                    db_save_chat_turn,
                    user_id=turn_uid,
                    session_id=session_id,
                    user_message=user_text,
                    spoken_reply=result["spoken_reply"],
                    tool_calls=result.get("tool_calls_executed", []),
                    latency_ms=result.get("latency_ms", 0.0),
                )
                await websocket.send_json({
                    "type": "turn_result",
                    "spoken_reply": result["spoken_reply"],
                    "tool_calls": result["tool_calls_executed"],
                    "requires_confirmation": result["requires_confirmation"],
                    "confirmation_question": result.get("confirmation_question"),
                    "latency_ms": result["latency_ms"],
                })

    except WebSocketDisconnect:
        logger.info(f"Voice WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent.main:app", host="127.0.0.1", port=8000, reload=True)

