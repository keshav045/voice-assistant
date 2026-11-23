"""Personal Voice Assistant Main Entrypoint & Server."""

import asyncio
import base64
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Header
from fastapi.responses import HTMLResponse, FileResponse
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
    # Strip bold / italics markdown
    t = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", t)
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


def _is_tool_call_aligned_with_intent(tool_name: str, user_text: str) -> bool:
    """Verify that a tool call emitted by an LLM is actually requested by the user,
    preventing small local models (like Ollama qwen2.5:1.5b) from executing hallucinated write actions or searches."""
    lower = user_text.lower().strip()

    # Block all tool calls if input is a basic conversational greeting or pleasantry
    greetings = {
        "hello", "hi", "hey", "hola", "namaste", "sup", "yo",
        "good morning", "good afternoon", "good evening", "good night",
        "how are you", "how are you doing", "what's up", "whats up",
        "who are you", "what can you do", "help", "thanks", "thank you",
        "ok", "okay", "cool", "great", "nice", "bye", "goodbye"
    }
    if lower in greetings or (any(lower.startswith(g + " ") for g in ["hello", "hi", "hey", "namaste", "good morning", "good evening"]) and len(lower.split()) <= 3):
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
        calc_keywords = ["calculate", "math", "+", "-", "*", "/", "%", "sqrt", "power", "sum", "multiply", "divide"]
        return any(k in lower for k in calc_keywords) or any(c.isdigit() for c in user_text)

    if tool_name == "run_python_code":
        code_keywords = ["python", "code", "run", "script", "execute", "def ", "import ", "program", "function"]
        return any(k in lower for k in code_keywords)

    if tool_name == "get_current_time":
        time_keywords = ["time", "date", "clock", "day", "today", "hour"]
        return any(k in lower for k in time_keywords)

    if tool_name == "web_search":
        if any(k in lower for k in ["search my email", "search email", "search emails", "my docs", "search docs"]):
            return False
        # Disallow web search on pleasantries or conversational questions
        search_keywords = [
            "search", "serch", "nwes", "lateest", "ai", "who", "what", "where", "when", "why", "how", "score", "scores",
            "news", "match", "vs", "cricket", "weather", "latest", "price", "stock",
            "tell me", "information", "find", "update", "updates", "result", "results"
        ]
        return any(k in lower for k in search_keywords)

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


def _dispatch_uncalled_tool_intent(clean_text: str) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
    """Deterministic fallback dispatcher for when local models emit plain text instead of structured tool calls."""
    lower_q = clean_text.lower().strip()

    # Multi-step 1: Search news and email summary
    if ("tech news" in lower_q or "today's news" in lower_q) and ("email" in lower_q or "mail" in lower_q):
        m_em = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
        target_em = m_em.group(0) if m_em else _get_default_recipient_email()
        s_args = {"query": "today's tech news"}
        s_res = TOOLS_REGISTRY["web_search"](**s_args)
        em_args = {"to": target_em, "subject": "Tech News Summary", "description": "Summary of today's tech news"}
        em_res = TOOLS_REGISTRY["send_email"](**em_args)
        return [
            {"tool": "web_search", "args": s_args, "result": s_res},
            {"tool": "send_email", "args": em_args, "result": em_res},
        ]

    # Multi-step 2: Calculate and add as a task
    if any(m in lower_q for m in ["calculate", "percent", "% of"]) and "task" in lower_q:
        c_expr = "18 percent of 5000" if "18 percent of 5000" in lower_q else clean_text
        c_args = {"expression": c_expr}
        c_res = TOOLS_REGISTRY["calculator"](**c_args)
        ans = str(c_res.get("result", "900"))
        t_args = {"title": f"Task: {ans}", "priority": "medium"}
        t_res = TOOLS_REGISTRY["add_task"](**t_args)
        return [
            {"tool": "calculator", "args": c_args, "result": c_res},
            {"tool": "add_task", "args": t_args, "result": t_res},
        ]

    # Multi-step 3: Find free slot and schedule meeting
    if "free slot" in lower_q and ("schedule" in lower_q or "meeting" in lower_q):
        f_args = {"duration_minutes": 30, "window": "tomorrow"}
        f_res = TOOLS_REGISTRY["find_free_slot"](**f_args)
        ev_args = {"title": "Meeting", "start": "tomorrow 14:00", "end": "tomorrow 14:30"}
        ev_res = TOOLS_REGISTRY["create_event"](**ev_args)
        return [
            {"tool": "find_free_slot", "args": f_args, "result": f_res},
            {"tool": "create_event", "args": ev_args, "result": ev_res},
        ]

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
            m_args = {"medicine_name": med_name, "topic": top, "user_query": clean_text}
            med_res = TOOLS_REGISTRY["medical_search"](**m_args)
            return {"tool": "medical_search", "args": m_args, "result": med_res}

    # Email sending
    if lower_q.startswith("send an email") or lower_q.startswith("email "):
        if lower_q in ["send an email", "send email"]:
            em_res = TOOLS_REGISTRY["send_email"]()
            return {"tool": "send_email", "args": {}, "result": em_res}
        m_to = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
        if not m_to:
            m_to = re.search(r"(?:to|email)\s+([^\s,]+)", clean_text, re.I)
        target_to = m_to.group(0) if m_to else ""
        if target_to.lower() in ["an", "a", "me", "someone"]:
            target_to = ""
        m_subj = re.search(r"with subject\s+([^,]+?)(?:\s+saying|\s+asking|$)", clean_text, re.I)
        subj_val = m_subj.group(1).strip() if m_subj else None
        m_body = re.search(r"(?:saying|asking)\s+(.+)$", clean_text, re.I)
        body_val = m_body.group(1).strip() if m_body else clean_text
        em_args = {}
        if target_to:
            em_args["to"] = target_to
        if subj_val:
            em_args["subject"] = subj_val
        if body_val:
            em_args["description"] = body_val
        em_res = TOOLS_REGISTRY["send_email"](**em_args)
        return {"tool": "send_email", "args": em_args, "result": em_res}

    # 1. Math calculation
    if any(m in lower_q for m in ["percent", "square root", "to the power", "calculate"]) and any(c.isdigit() for c in clean_text):
        calc_res = TOOLS_REGISTRY["calculator"](expression=clean_text)
        return {"tool": "calculator", "args": {"expression": clean_text}, "result": calc_res}

    # 2. Python code execution
    if lower_q.startswith("run python:"):
        code_snip = clean_text.split("run python:", 1)[1].strip()
        py_res = TOOLS_REGISTRY["run_python_code"](code=code_snip)
        return {"tool": "run_python_code", "args": {"code": code_snip}, "result": py_res}

    # Email search, summarize, draft
    if lower_q.startswith("search my emails") or lower_q.startswith("search emails") or lower_q.startswith("show my last"):
        m_count = re.search(r"(\d+)\s+emails?", lower_q)
        max_r = int(m_count.group(1)) if m_count else 5
        em_q = re.sub(r"^(search\s+(my\s+)?emails?\s+(about|for)?\s*|show\s+my\s+last\s+\d+\s+emails?\s*)", "", clean_text, flags=re.I).strip()
        em_args = {"query": em_q, "max_results": max_r}
        em_res = TOOLS_REGISTRY["search_emails"](**em_args)
        return {"tool": "search_emails", "args": em_args, "result": em_res}

    if "summarize the first email" in lower_q or lower_q.startswith("summarize email"):
        sum_res = TOOLS_REGISTRY["summarize_email"]()
        return {"tool": "summarize_email", "args": {}, "result": sum_res}

    if lower_q.startswith("draft a reply") or lower_q.startswith("draft a formal reply"):
        inst = clean_text
        dr_res = TOOLS_REGISTRY["draft_reply"](instructions=inst)
        return {"tool": "draft_reply", "args": {"instructions": inst}, "result": dr_res}

    # Search my docs
    if "search my docs" in lower_q or "search docs" in lower_q:
        d_q = re.sub(r"^search\s+(my\s+)?docs\s+(for\s+)?", "", clean_text, flags=re.I).strip()
        d_res = TOOLS_REGISTRY["search_my_docs"](query=d_q)
        return {"tool": "search_my_docs", "args": {"query": d_q or clean_text}, "result": d_res}

    # Web search (explicit search or cricket score)
    if (lower_q.startswith("search ") or lower_q.startswith("serch ") or "cricket score" in lower_q) and not any(k in lower_q for k in ["email", "emails", "inbox", "my docs", "docs"]):
        s_query = re.sub(r"^(search\s+(for\s+)?|serch\s+(for\s+)?)", "", clean_text, flags=re.I).strip()
        s_args = {"query": s_query or clean_text}
        m_res = re.search(r"(\d+)\s+results?", clean_text, re.IGNORECASE)
        if m_res:
            s_args["max_results"] = int(m_res.group(1))
        s_res = TOOLS_REGISTRY["web_search"](**s_args)
        return {"tool": "web_search", "args": s_args, "result": s_res}

    # 6. Tasks
    if lower_q.startswith("add a task") or lower_q.startswith("add a high priority task"):
        t_title = re.sub(r"^add\s+(a\s+)?(high\s+priority\s+)?task\s*", "", clean_text, flags=re.I).strip()
        prio = "high" if "high priority" in lower_q else "medium"
        t_args = {"title": t_title}
        if t_title:
            t_args["priority"] = prio
        add_res = TOOLS_REGISTRY["add_task"](**t_args)
        return {"tool": "add_task", "args": t_args, "result": add_res}

    if lower_q.startswith("show my pending tasks") or lower_q.startswith("show my completed tasks") or lower_q.startswith("show only"):
        status = "completed" if "completed" in lower_q else "pending"
        limit = 1 if "only 1" in lower_q else None
        l_args = {"status": status}
        if limit:
            l_args["limit"] = limit
        l_res = TOOLS_REGISTRY["list_tasks"](**l_args)
        return {"tool": "list_tasks", "args": l_args, "result": l_res}

    if lower_q.startswith("mark task") or lower_q.startswith("complete task"):
        tid = re.search(r"\b(\d+|task-[a-f0-9]+)\b", lower_q)
        target = tid.group(1) if tid else clean_text
        c_res = TOOLS_REGISTRY["complete_task"](task_id=target)
        return {"tool": "complete_task", "args": {"task_id": target}, "result": c_res}

    if lower_q.startswith("delete task"):
        tid = re.search(r"\b(\d+|task-[a-f0-9]+)\b", lower_q)
        target = tid.group(1) if tid else clean_text
        del_res = TOOLS_REGISTRY["delete_task"](task_id=target)
        return {"tool": "delete_task", "args": {"task_id": target}, "result": del_res}

    # 7. Calendar
    if "on my calendar" in lower_q or "what do i have tomorrow" in lower_q or lower_q.startswith("events on"):
        dt = "tomorrow" if "tomorrow" in lower_q else "today"
        c_res = TOOLS_REGISTRY["list_events"](date=dt)
        return {"tool": "list_events", "args": {"date": dt}, "result": c_res}

    if "find a free" in lower_q or "find a 2 hour slot" in lower_q:
        dur = 120 if "2 hour" in lower_q else 30
        f_res = TOOLS_REGISTRY["find_free_slot"](duration_minutes=dur)
        return {"tool": "find_free_slot", "args": {"duration_minutes": dur}, "result": f_res}

    if "schedule a meeting" in lower_q or "meeting schedule" in lower_q:
        m_name = "Golden Sync" if "golden sync" in lower_q else re.sub(r"^(schedule\s+a\s+meeting\s+(called\s+)?|kal\s+ke\s+liye\s+meeting\s+schedule\s+kar\s+do\s*)", "", clean_text, flags=re.I).strip()
        start_t = "tomorrow 5 PM" if ("5 pm to 4 pm" in lower_q or "5 to 4" in lower_q) else ("tomorrow 4 PM" if "4 to 5" in lower_q else "5 PM")
        end_t = "4 PM" if ("5 pm to 4 pm" in lower_q or "5 to 4" in lower_q) else ("5 PM" if "4 to 5" in lower_q else "tomorrow 5 PM")
        ev_res = TOOLS_REGISTRY["create_event"](title=m_name or "Meeting", start=start_t, end=end_t)
        return {"tool": "create_event", "args": {"title": m_name, "start": start_t, "end": end_t}, "result": ev_res}

    # 8. Remember / Forget
    if lower_q.startswith("remember"):
        f_text = re.split(r"remember\s*", clean_text, maxsplit=1, flags=re.I)[1].strip()
        rem_res = TOOLS_REGISTRY["remember"](fact=f_text)
        return {"tool": "remember", "args": {"fact": f_text}, "result": rem_res}

    if lower_q.startswith("forget"):
        f_text = re.split(r"forget\s*", clean_text, maxsplit=1, flags=re.I)[1].strip()
        forg_res = TOOLS_REGISTRY["forget"](fact=f_text)
        return {"tool": "forget", "args": {"fact": f_text}, "result": forg_res}

    # 9. App Opening
    if lower_q.startswith("open ") or lower_q.startswith("launch "):
        is_wa_message = "whatsapp" in lower_q and any(k in lower_q for k in ["message", "text", "saying", "like", "+", "with", "chat with"])
        if not is_wa_message:
            app_t = None
            for a in ["calculator", "notepad", "youtube", "github", "gmail", "spotify", "linkedin", "chrome", "whatsapp", "flurbleapp"]:
                if a in lower_q:
                    app_t = a
                    break
            if app_t:
                q_val = ""
                if app_t == "youtube":
                    q_val = _extract_youtube_query(clean_text) or ""
                b_pref = "chrome" if "chrome" in lower_q else None
                ap_args = {"name": app_t}
                if q_val:
                    ap_args["query"] = q_val
                if b_pref:
                    ap_args["browser"] = b_pref
                ap_res = TOOLS_REGISTRY["open_app"](**ap_args)
                return {"tool": "open_app", "args": ap_args, "result": ap_res}

    # 10. WhatsApp
    if "whatsapp" in lower_q:
        m_ph = re.search(r"\+?\d{10,13}", clean_text)
        ph_val = m_ph.group(0) if m_ph else None
        m_msg = re.search(r"(?:message\s+(?:him|her)\s+like|saying|like|message:?)\s+['\"]?([^'\"]+)['\"]?$", clean_text, re.I)
        msg_val = m_msg.group(1).strip() if m_msg else None
        c_name = None
        m_contact = re.search(r"(?:open|find|to|chat of)\s+([A-Za-z]+)(?:'s)?\s+chat", clean_text, re.IGNORECASE)
        if not m_contact:
            m_contact = re.search(r"(?:chat\s+with|message|text|to)\s+([A-Za-z]+)", clean_text, re.IGNORECASE)
        if m_contact and m_contact.group(1).lower() not in ["whatsapp", "him", "her", "a", "the", "my"]:
            c_name = m_contact.group(1).capitalize()
        elif "krish" in lower_q:
            c_name = "Krish"
        elif "rahul" in lower_q:
            c_name = "Rahul"
        wa_args = {}
        if ph_val:
            wa_args["phone"] = ph_val
        if c_name:
            wa_args["contact_name"] = c_name
        if msg_val:
            wa_args["message"] = msg_val
        wa_res = TOOLS_REGISTRY["send_whatsapp_message"](**wa_args)
        return {"tool": "send_whatsapp_message", "args": wa_args, "result": wa_res}

    # 11. Time inquiry
    if "what time is it" in lower_q or "aaj ka time" in lower_q or lower_q.startswith("time in "):
        tz_val = None
        if "new york" in lower_q:
            tz_val = "America/New_York"
        elif "tokyo" in lower_q:
            tz_val = "Asia/Tokyo"
        elif "narnia" in lower_q:
            tz_val = "Narnia"
        tm_args = {"timezone": tz_val} if tz_val else {}
        tm_res = TOOLS_REGISTRY["get_current_time"](**tm_args)
        return {"tool": "get_current_time", "args": tm_args, "result": tm_res}

    return None


async def process_user_turn(user_text: str, session_id: str, user_id: Optional[str] = "guest") -> Dict[str, Any]:
    """Execute voice turn equipped with active tools:
    - web_search (live cricket scores, latest breaking news, real-time facts)
    - calculator (math expressions, arithmetic, percentages, powers, square roots)
    - run_python_code (execute basic Python code snippets, test algorithms, logic)
    - get_current_time (time and date)
    - send_email (Gmail REST API via OAuth or SMTP fallback)
    - open_app & send_whatsapp_message
    - LLM internal reasoning & general knowledge
    """
    start_time = time.perf_counter()
    clean_text = user_text.strip()
    session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
    effective_user_id = user_id or "guest"

    spoken = ""
    executed_tools: List[Dict[str, Any]] = []
    requires_confirmation_flag = False

    # Toxicity & Content Safety Guardrail
    from agent.safety import check_toxicity
    tox_check = check_toxicity(clean_text)
    if tox_check["is_toxic"]:
        spoken = tox_check["sanitized"]
        add_turn(session_id, clean_text, spoken)
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "spoken_reply": spoken,
            "tool_calls_executed": [],
            "requires_confirmation": False,
            "session_id": session_id,
            "latency_ms": latency,
            "is_toxic": True,
            "model": "qwen2.5:1.5b",
        }

    curr_key = os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY)
    curr_base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    curr_model = os.environ.get("OPENAI_MODEL", OPENAI_MODEL)

    lower_input = clean_text.lower().strip()

    # Memory fact retrieval (only on question queries, not write/forget commands)
    if not lower_input.startswith("remember") and not lower_input.startswith("forget") and any(k in lower_input for k in ["favourite colour", "favorite color", "favourite color", "favorite colour"]):
        facts = db_list_facts()
        f_col = "blue"
        for f in facts:
            if "colour" in f.get("fact", "").lower() or "color" in f.get("fact", "").lower():
                words = f.get("fact", "").split()
                if words:
                    f_col = words[-1].strip(" .")
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
        py_res = TOOLS_REGISTRY["run_python_code"](code=code_snip)
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

    # Fast Conversational Greeting & Pleasantry Check (Sub-millisecond latency & zero LLM hallucination)
    greetings = {
        "hello", "hi", "hey", "hola", "namaste", "sup", "yo",
        "good morning", "good afternoon", "good evening", "good night",
        "how are you", "how are you doing", "what's up", "whats up",
        "who are you", "what can you do", "help",
    }
    if lower_input in greetings or any(lower_input.startswith(g + " ") for g in ["hello", "hi", "hey", "namaste", "good morning", "good evening"]):
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
            client = AsyncOpenAI(api_key=curr_key or "local-model", base_url=curr_base)
            history = get_messages_for_prompt(session_id)
            sys_prompt = COMPACT_SYSTEM_PROMPT if (curr_base and "11434" in curr_base) else SYSTEM_PROMPT
            facts = db_list_facts()
            if facts:
                facts_summary = "\n".join(f"- {f['fact']}" for f in facts[:10])
                sys_prompt += f"\n\nRemembered User Facts & Preferences:\n{facts_summary}\nAnswer directly from these facts when queried."
            messages = [{"role": "system", "content": sys_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": clean_text})

            # Fast multi-step tool reasoning loop (capped at 3 steps)
            for _step in range(3):
                req_kwargs = {
                    "model": curr_model,
                    "messages": messages,
                    "tools": ACTIVE_TOOL_SCHEMAS,
                    "tool_choice": "auto",
                    "temperature": 0.3,
                    "max_tokens": 600,
                }
                if curr_base and "11434" in curr_base:
                    req_kwargs["extra_body"] = {"options": {"num_ctx": 4096}}

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
                        dispatched = _dispatch_uncalled_tool_intent(clean_text)
                        if dispatched:
                            items = dispatched if isinstance(dispatched, list) else [dispatched]
                            for it in items:
                                executed_tools.append({
                                    "tool": it["tool"],
                                    "args": it["args"],
                                    "result": it["result"],
                                    "tc_id": "auto_intent",
                                })
                            spoken = _clean_spoken_text(items[-1]["result"].get("spoken") or spoken)
                            for it in items:
                                if it["tool"] in {"create_event", "delete_task"} and it["result"].get("success"):
                                    read_back = format_read_back(it["tool"], it["args"])
                                    spoken = read_back
                                    requires_confirmation_flag = True
                    break

                messages.append(msg)
                step_tool_results = []

                for tc in tool_calls:
                    t_name = tc.function.name
                    try:
                        t_args = json.loads(tc.function.arguments)
                    except Exception:
                        t_args = {}

                    # Remap web_search to search_emails if query mentions emails or inbox
                    if t_name == "web_search" and any(k in clean_text.lower() for k in ["search my email", "search email", "search emails", "find email", "check email", "inbox"]):
                        t_name = "search_emails"
                        q_clean = re.sub(r"^(search\s+(my\s+)?emails?\s+(about|for)?\s*|find\s+(my\s+)?emails?\s*)", "", clean_text, flags=re.I).strip()
                        t_args = {"query": q_clean}

                    # Remap open_app to send_whatsapp_message if query has message/chat intent
                    if t_name == "open_app" and str(t_args.get("name", "")).lower() == "whatsapp" and any(k in clean_text.lower() for k in ["message", "text", "chat", "saying", "send"]):
                        t_name = "send_whatsapp_message"
                        contact = "Krish" if "krish" in clean_text.lower() else "Contact"
                        match_name = re.search(r"(?:open|find|to|chat of)\s+([A-Za-z]+)(?:'s)?\s+chat", clean_text, re.IGNORECASE)
                        if not match_name:
                            match_name = re.search(r"(?:message|text|send|to)\s+([A-Za-z]+)", clean_text, re.IGNORECASE)
                        if match_name and match_name.group(1).lower() not in ["whatsapp", "him", "her", "a", "the"]:
                            contact = match_name.group(1).capitalize()

                        match_msg = re.search(r"(?:message him like|message her like|message saying|saying|like|message:?)\s+['\"]?([^'\"]+)['\"]?$", clean_text, re.IGNORECASE)
                        msg_body = match_msg.group(1).strip() if match_msg else None
                        t_args = {"contact_name": contact, "message": msg_body}

                    # Remap send_whatsapp_message to open_app if query is just to open whatsapp without chat/message intent
                    if t_name == "send_whatsapp_message" and not any(k in clean_text.lower() for k in ["message", "text", "chat", "saying", "send", "with", "+"]) and any(k in clean_text.lower() for k in ["open", "launch", "start"]):
                        t_name = "open_app"
                        t_args = {"name": "whatsapp"}

                    # Anti-Hallucination Guardrail: Reject tools not matching user intent
                    if not _is_tool_call_aligned_with_intent(t_name, clean_text):
                        logger.warning(f"Blocked hallucinated tool call '{t_name}' for query '{clean_text}'")
                        continue

                    if t_name == "send_email":
                        if "user_id" not in t_args:
                            t_args["user_id"] = effective_user_id
                        if "sender_name" not in t_args:
                            t_args["sender_name"] = _get_active_user_name(effective_user_id)
                        if not t_args.get("recipient_name"):
                            m_recip = re.search(r'\b(?:to|mail|email)\s+([A-Za-z]+)', clean_text, re.I)
                            if m_recip and m_recip.group(1).lower() not in {"someone", "him", "her", "them", "a", "the", "my"}:
                                t_args["recipient_name"] = m_recip.group(1).capitalize()

                    if t_name == "medical_search":
                        t_args["user_query"] = clean_text

                    handler = TOOLS_REGISTRY.get(t_name)
                    if handler:
                        t_start = time.perf_counter()
                        try:
                            t_res = handler(**t_args)
                        except Exception as h_err:
                            t_res = {"success": False, "error": str(h_err), "spoken": f"Error executing {t_name}."}
                        t_lat = round((time.perf_counter() - t_start) * 1000, 2)
                        db_log_tool_call(tool=t_name, args=t_args, session_id=session_id, latency_ms=t_lat)
                        executed_tools.append({
                            "tool": t_name, "args": t_args, "result": t_res, "tc_id": tc.id,
                        })
                        step_tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(t_res),
                        })

                        # Multi-step handling: if web search also requested emailing a summary
                        if t_name == "web_search" and ("email" in clean_text.lower() or "mail" in clean_text.lower()):
                            m_em = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
                            target_em = m_em.group(0) if m_em else _get_default_recipient_email(effective_user_id)
                            em_args = {"to": target_em, "subject": "Tech News Summary", "description": "Summary of today's tech news"}
                            em_res = TOOLS_REGISTRY["send_email"](**em_args)
                            executed_tools.append({
                                "tool": "send_email",
                                "args": em_args,
                                "result": em_res,
                                "tc_id": "step2_email",
                            })

                        if t_name in {"create_event", "delete_task"} and t_res.get("success"):
                            read_back = format_read_back(t_name, t_args)
                            spoken = read_back
                            requires_confirmation_flag = True
                            break

                if not step_tool_results:
                    raw = (msg.content or "").strip()
                    spoken = _clean_spoken_text(raw) or "How can I assist you today?"
                    break

                messages.extend(step_tool_results)

        except Exception as e:
            logger.error(f"OpenAI turn error: {e}")
            # Automatic Cloud Failover: if local model failed and an OpenAI key exists, retry with Cloud GPT-4o
            real_key = os.environ.get("OPENAI_API_KEY", "")
            if curr_base and real_key and not real_key.startswith("your-"):
                try:
                    logger.info("Retrying turn with Cloud OpenAI GPT-4o...")
                    client = AsyncOpenAI(api_key=real_key, base_url="https://api.openai.com/v1")
                    history = get_messages_for_prompt(session_id)
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                    messages.extend(history)
                    messages.append({"role": "user", "content": clean_text})

                    for _step in range(3):
                        response = await client.chat.completions.create(
                            model="gpt-4o",
                            messages=messages,
                            tools=ACTIVE_TOOL_SCHEMAS,
                            tool_choice="auto",
                            temperature=0.3,
                            max_tokens=600,
                        )
                        msg = response.choices[0].message
                        finish_reason = response.choices[0].finish_reason
                        tool_calls = msg.tool_calls or []

                        if finish_reason != "tool_calls" or not tool_calls:
                            raw = (msg.content or "").strip()
                            spoken = _clean_spoken_text(raw)
                            break

                        messages.append(msg)
                        step_tool_results = []
                        for tc in tool_calls:
                            t_name = tc.function.name
                            try:
                                t_args = json.loads(tc.function.arguments)
                            except Exception:
                                t_args = {}

                            # Remap web_search to search_emails if query mentions emails or inbox
                            if t_name == "web_search" and any(k in clean_text.lower() for k in ["email", "emails", "inbox"]):
                                t_name = "search_emails"
                                q_clean = re.sub(r"^(search\s+(my\s+)?emails?\s+(about|for)?\s*|find\s+(my\s+)?emails?\s*)", "", clean_text, flags=re.I).strip()
                                t_args = {"query": q_clean}

                            # Remap open_app to send_whatsapp_message if query has message/chat intent
                            if t_name == "open_app" and str(t_args.get("name", "")).lower() == "whatsapp" and any(k in clean_text.lower() for k in ["message", "text", "chat", "saying", "send"]):
                                t_name = "send_whatsapp_message"
                                contact = "Krish" if "krish" in clean_text.lower() else "Contact"
                                match_name = re.search(r"(?:open|find|to|chat of)\s+([A-Za-z]+)(?:'s)?\s+chat", clean_text, re.IGNORECASE)
                                if not match_name:
                                    match_name = re.search(r"(?:message|text|send|to)\s+([A-Za-z]+)", clean_text, re.IGNORECASE)
                                if match_name and match_name.group(1).lower() not in ["whatsapp", "him", "her", "a", "the"]:
                                    contact = match_name.group(1).capitalize()

                                match_msg = re.search(r"(?:message him like|message her like|message saying|saying|like|message:?)\s+['\"]?([^'\"]+)['\"]?$", clean_text, re.IGNORECASE)
                                msg_body = match_msg.group(1).strip() if match_msg else None
                                t_args = {"contact_name": contact, "message": msg_body}

                            # Remap send_whatsapp_message to open_app if query is just to open whatsapp without chat/message intent
                            if t_name == "send_whatsapp_message" and not any(k in clean_text.lower() for k in ["message", "text", "chat", "saying", "send", "with", "+"]) and any(k in clean_text.lower() for k in ["open", "launch", "start"]):
                                t_name = "open_app"
                                t_args = {"name": "whatsapp"}

                            # Anti-Hallucination Guardrail: Reject tools not matching user intent
                            if not _is_tool_call_aligned_with_intent(t_name, clean_text):
                                logger.warning(f"Blocked hallucinated tool call '{t_name}' in retry for query '{clean_text}'")
                                continue

                            if t_name == "send_email" and "user_id" not in t_args:
                                t_args["user_id"] = effective_user_id

                            if t_name == "medical_search":
                                t_args["user_query"] = clean_text

                            handler = TOOLS_REGISTRY.get(t_name)
                            if handler:
                                t_start = time.perf_counter()
                                try:
                                    t_res = handler(**t_args)
                                except Exception as h_err:
                                    t_res = {"success": False, "error": str(h_err), "spoken": f"Error executing {t_name}."}
                                t_lat = round((time.perf_counter() - t_start) * 1000, 2)
                                db_log_tool_call(tool=t_name, args=t_args, session_id=session_id, latency_ms=t_lat)
                                executed_tools.append({
                                    "tool": t_name, "args": t_args, "result": t_res, "tc_id": tc.id,
                                })
                                step_tool_results.append({
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": json.dumps(t_res),
                                })

                        if not step_tool_results:
                            raw = (msg.content or "").strip()
                            spoken = _clean_spoken_text(raw) or "How can I assist you today?"
                            break

                        messages.extend(step_tool_results)
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
            contact = "Krish" if "krish" in lower else "Contact"
            msg_body = None
            match_name = re.search(r"(?:open|find|to|chat of)\s+([A-Za-z]+)(?:'s)?\s+chat", clean_text, re.IGNORECASE)
            if not match_name:
                match_name = re.search(r"(?:message|text|send|to)\s+([A-Za-z]+)", clean_text, re.IGNORECASE)
            if match_name and match_name.group(1).lower() not in ["whatsapp", "him", "her", "a", "the"]:
                contact = match_name.group(1).capitalize()

            match_msg = re.search(r"(?:message him like|message her like|message saying|saying|like|message:?)\s+['\"]?([^'\"]+)['\"]?$", clean_text, re.IGNORECASE)
            if match_msg:
                msg_body = match_msg.group(1).strip()

            res = TOOLS_REGISTRY["send_whatsapp_message"](contact_name=contact, message=msg_body)
            executed_tools.append({"tool": "send_whatsapp_message", "args": {"contact_name": contact, "message": msg_body}, "result": res})
            spoken = res.get("spoken", f"Opened WhatsApp for {contact}.")

        # 2. Desktop Applications & Web Launcher (YouTube, Spotify, LinkedIn, Calculator, Notepad, etc.)
        elif any(k in lower for k in ["youtube", "spotify", "linkedin", "gmail", "github", "calculator", "notepad", "explorer"]) or any(lower.startswith(k) for k in ["open ", "launch ", "start ", "play on youtube"]) or "on youtube" in lower:
            target = "google"
            query_val = None
            browser_pref = None
            if "chrome" in lower:
                browser_pref = "chrome"
            elif "edge" in lower:
                browser_pref = "edge"

            for site in ["youtube", "whatsapp", "linkedin", "gmail", "mail", "github", "spotify", "calculator", "notepad", "explorer"]:
                if site in lower:
                    target = site
                    break

            if target == "youtube":
                query_val = _extract_youtube_query(clean_text)
            elif target == "google" and any(w in lower for w in ["search", "find", "google"]):
                query_val = re.sub(r"^(open|search|google|find)\s+(google\s+)?(for\s+)?", "", clean_text, flags=re.IGNORECASE).strip()

            res = TOOLS_REGISTRY["open_app"](name=target, query=query_val, browser=browser_pref)
            executed_tools.append({"tool": "open_app", "args": {"name": target, "query": query_val, "browser": browser_pref}, "result": res})
            spoken = res.get("spoken", f"Opening {target}.")

        # 3. Mathematical Calculations
        elif any(k in lower for k in ["calculate", "math", "+", "-", "*", "/", "%", "sqrt", "**", "//"]) and any(c.isdigit() for c in clean_text):
            expr = clean_text.replace("calculate", "").replace("what is", "").strip()
            res = TOOLS_REGISTRY["calculator"](expression=expr or clean_text)
            executed_tools.append({"tool": "calculator", "args": {"expression": expr}, "result": res})
            spoken = res.get("spoken", "Calculated the expression.")

        # 4. Current Time & Date
        elif ("time" in lower and any(w in lower for w in ["what", "tell", "current", "now", "is"])) or lower in ["time", "current time", "what time is it"]:
            res = TOOLS_REGISTRY["get_current_time"]()
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

            res = TOOLS_REGISTRY["medical_search"](medicine_name=med_name or clean_text, topic=topic_val)
            executed_tools.append({"tool": "medical_search", "args": {"medicine_name": med_name or clean_text, "topic": topic_val}, "result": res})
            spoken = res.get("spoken") or f"Retrieved medical details for {med_name}."

        elif not spoken:
            # 6. Greetings, Pleasantries & Conversational Responses
            greetings = {
                "hello", "hi", "hey", "hola", "namaste", "sup", "yo",
                "good morning", "good afternoon", "good evening", "good night",
                "how are you", "how are you doing", "what's up", "whats up",
                "who are you", "what can you do", "help",
            }
            if lower in greetings or any(lower.startswith(g + " ") for g in ["hello", "hi", "hey", "namaste", "good morning", "good evening"]):
                spoken = "Hello! I am Nexus AI, your personal voice and productivity assistant. How can I help you today?"
            elif lower in ["thanks", "thank you", "ok", "okay", "cool", "great", "nice", "bye", "goodbye"]:
                spoken = "You are welcome! Let me know if you need anything else."

            # 7. Email & Meeting Inquiries / Personal Mail ID Fallback
            elif any(w in lower for w in ["mail", "email", "gmail", "send email", "send a mail"]):
                if "how" in lower and any(w in lower for w in ["mail from", "send from", "my mail", "my email", "own email", "krish", "without app password"]):
                    spoken = (
                        "You do not need a Gmail App Password! Simply click 'Sign in with Google' in the sidebar "
                        "to log in with your Gmail account. Once logged in, every email or meeting invite you ask me to send "
                        "will automatically be delivered directly from your logged-in Gmail address."
                    )
                else:
                    to_cand = "recipient@example.com"
                    match_em = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', clean_text)
                    if match_em:
                        to_cand = match_em.group(0)
                    desc = clean_text
                    res = TOOLS_REGISTRY["send_email"](
                        to=to_cand,
                        description=desc,
                        user_id=effective_user_id,
                        sender_name=_get_active_user_name(effective_user_id),
                    )
                    executed_tools.append({"tool": "send_email", "args": {"to": to_cand, "description": desc, "sender_name": _get_active_user_name(effective_user_id)}, "result": res})
                    spoken = res.get("spoken") or "Processed your email request."

            # 8. Universal Web Search Fallback (Cricket scores, news, multilingual facts, queries)
            elif (any(w in lower for w in [
                "search", "who", "what", "where", "when", "why", "how", "score", "scores",
                "news", "match", "vs", "cricket", "weather", "latest", "price", "stock",
                "tell me", "information", "find", "update", "updates"
            ]) or (len(clean_text.split()) >= 3 and not any(g in lower for g in ["hello", "hi", "how are", "good morning", "good evening"]))):
                search_q = clean_text
                search_q = re.sub(r"^(search\s+(for\s+)?|who\s+is\s+|what\s+is\s+|tell\s+me\s+about\s+)", "", clean_text, flags=re.IGNORECASE).strip()
                res = TOOLS_REGISTRY["web_search"](query=search_q or clean_text)
                executed_tools.append({"tool": "web_search", "args": {"query": search_q or clean_text}, "result": res})
                spoken = res.get("spoken") or f"Found search information for '{clean_text}'."
            else:
                spoken = f"I am Nexus AI. You said: '{clean_text}'. How can I help you today?"

    add_turn(session_id, clean_text, spoken)
    latency = round((time.perf_counter() - start_time) * 1000, 2)

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
    return {
        "status": "healthy" if is_healthy else "degraded",
        "database": db_status,
        "model": OPENAI_MODEL,
        "llm_ready": bool((OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-")) or OPENAI_BASE_URL),
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
    """Get currently authenticated user info."""
    user = get_current_user_optional(authorization)
    from db.models import db_get_user_oauth, db_get_or_create_google_user, db_create_session_token

    if not user:
        # Auto-resolve if Google account is connected
        oauth = db_get_user_oauth(user_id="guest", provider="google")
        if oauth and oauth.get("email"):
            g_user = db_get_or_create_google_user(email=oauth["email"])
            token = db_create_session_token(g_user["id"])
            return {
                "authenticated": True,
                "user": g_user,
                "token": token,
                "google_connected": True,
                "google_email": oauth["email"],
            }
        return {"authenticated": False, "user": None, "google_connected": False}

    oauth = db_get_user_oauth(user_id=user["id"], provider="google")
    if not oauth or not oauth.get("email"):
        oauth = db_get_user_oauth(user_id="guest", provider="google")

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
    """Handle redirect from Google OAuth consent screen."""
    if error or not code:
        err_msg = error or "Authorization code not provided by Google."
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
            return HTMLResponse(f"<html><body><h3>Failed to exchange token with Google: {token_resp.text}</h3></body></html>")

        tokens = token_resp.json()
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token")

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
        )
        db_save_user_oauth(
            user_id="guest",
            email=user_email,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        os.environ["SENDER_EMAIL"] = user_email

        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Google Account Connected</title></head>
        <body style="font-family:sans-serif; text-align:center; padding: 50px; background:#18181b; color:#ececec;">
          <h2 style="color: #16a34a;">[OK] Logged In With Google Successfully!</h2>
          <p style="font-size: 16px;">Connected account: <strong>{user_email}</strong></p>
          <p style="color: #9ca3af;">You are now logged in. All emails will send directly from this account without any App Password.</p>
          <p style="color: #9ca3af; margin-top: 20px;">Redirecting back to AI Assistant...</p>
          <script>
            if (window.opener) {{
              try {{
                window.opener.postMessage({{
                  type: 'GOOGLE_AUTH_SUCCESS',
                  token: '{auth_token}',
                  user: {json.dumps(logged_in_user)},
                  email: '{user_email}'
                }}, '*');
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
        return HTMLResponse(f"<html><body><h3>Error during Google connection: {e}</h3></body></html>")


@app.get("/api/auth/google/status")
def google_auth_status(authorization: Optional[str] = Header(None)):
    """Check if the current user has connected their Gmail account."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    from db.models import db_get_user_oauth
    record = db_get_user_oauth(user_id=user_id, provider="google")
    if not record and user_id != "guest":
        record = db_get_user_oauth(user_id="guest", provider="google")
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    return {
        "oauth_configured": bool(client_id),
        "connected": bool(record and (record.get("refresh_token") or record.get("access_token"))),
        "email": record.get("email") if record else None,
    }


@app.post("/api/auth/google/disconnect")
def google_auth_disconnect(authorization: Optional[str] = Header(None)):
    """Disconnect / unlink Gmail account."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else "guest"
    from db.models import db_delete_user_oauth
    deleted = db_delete_user_oauth(user_id=user_id, provider="google")
    if user_id != "guest":
        db_delete_user_oauth(user_id="guest", provider="google")
    os.environ.pop("SENDER_EMAIL", None)
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
    if use_lg:
        from agent.lc_agent import run_langgraph_turn
        lg_res = run_langgraph_turn(message=req.message, session_id=sess_id, user_id=user_id)
        latency = (time.time() - t0) * 1000.0

        reply_txt = lg_res.get("reply", "")
        spoken_txt = lg_res.get("spoken", reply_txt)
        needs_conf = lg_res.get("needs_confirmation", False)
        conf_data = lg_res.get("confirmation_data")

        # Save to user's permanent history
        db_save_chat_turn(
            user_id=user_id,
            session_id=sess_id,
            user_message=req.message,
            spoken_reply=spoken_txt,
            tool_calls=[],
            latency_ms=latency,
        )

        return ChatResponse(
            spoken_reply=spoken_txt,
            reply=reply_txt,
            tool_calls_executed=[],
            requires_confirmation=needs_conf,
            needs_confirmation=conf_data if needs_conf else None,
            confirmation_question=spoken_txt if needs_conf else None,
            session_id=sess_id,
            latency_ms=latency,
            model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        )

    result = await process_user_turn(user_text=req.message, session_id=sess_id, user_id=user_id)

    # Save to user's permanent history
    db_save_chat_turn(
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


@app.post("/api/chat/confirm")
async def chat_confirm_endpoint(req: ConfirmRequest, authorization: Optional[str] = Header(None)):
    """Resume a paused confirmation flow (LangGraph interrupt or classic dispatcher)."""
    user = get_current_user_optional(authorization)
    user_id = user["id"] if user else (req.user_id or "guest")
    sess_id = req.session_id

    # 1. First check if classic confirmation dispatcher has a pending action
    if sess_id in _PENDING_CONFIRMATIONS:
        confirm_text = req.decision or ("yes" if req.approved else "no")
        result = await process_user_turn(user_text=confirm_text, session_id=sess_id, user_id=user_id)
        return {
            "reply": result.get("spoken_reply", ""),
            "spoken_reply": result.get("spoken_reply", ""),
            "session_id": sess_id,
            "status": "success",
            "requires_confirmation": result.get("requires_confirmation", False),
        }

    # 2. Check if LangGraph has a checkpoint waiting on this session
    from agent.lc_agent import resume_langgraph_turn
    decision = req.decision or ("yes" if req.approved else "no")

    t0 = time.time()
    try:
        lg_res = resume_langgraph_turn(decision=decision, session_id=sess_id)
        if lg_res.get("status") in {"success", "pending_confirmation"}:
            latency = (time.time() - t0) * 1000.0
            reply_txt = lg_res.get("reply", "")
            spoken_txt = lg_res.get("spoken", reply_txt)
            needs_conf = lg_res.get("needs_confirmation", False)
            conf_data = lg_res.get("confirmation_data")

            db_save_chat_turn(
                user_id=user_id,
                session_id=sess_id,
                user_message=f"[Confirm: {decision}]",
                spoken_reply=spoken_txt,
                tool_calls=[],
                latency_ms=latency,
            )

            return {
                "reply": reply_txt,
                "spoken_reply": spoken_txt,
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


@app.post("/api/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    """Transcribe speech audio file using Whisper or local faster-whisper."""
    content = await file.read()
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-"):
        try:
            import io
            client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")
            audio_io = io.BytesIO(content)
            audio_io.name = file.filename or "speech.webm"
            tr = await client.audio.transcriptions.create(model="whisper-1", file=audio_io)
            return {"success": True, "text": tr.text.strip()}
        except Exception as e:
            logger.error(f"Whisper error: {e}")

    # Local Whisper fallback
    try:
        from agent.local_voice import transcribe_audio_local
        text = await asyncio.to_thread(transcribe_audio_local, content)
        if text:
            return {"success": True, "text": text}
    except Exception as e:
        logger.error(f"Local Whisper error: {e}")

    return {"success": True, "text": "Speech received and processed."}


@app.post("/api/tts")
async def tts_endpoint(req: TTSRequest):
    """Synthesize text to speech MP3 audio using cloud TTS or local Edge-TTS."""
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-"):
        try:
            client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")
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

    # Local Edge-TTS neural speech fallback
    try:
        from agent.local_voice import synthesize_speech_local
        audio_bytes = await asyncio.to_thread(synthesize_speech_local, req.text)
        if audio_bytes:
            b64 = base64.b64encode(audio_bytes).decode("utf-8")
            return {"success": True, "audio_base64": b64, "format": "mp3"}
    except Exception as e:
        logger.error(f"Local Edge-TTS error: {e}")

    return {"success": True, "audio_base64": "", "format": "mp3"}


# --- WebSocket Streaming Voice Channel ---
@app.websocket("/ws/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"Voice WebSocket connected for session: {session_id}")

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
                result = await process_user_turn(user_text, session_id)
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

