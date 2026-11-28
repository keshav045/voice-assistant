"""Nexus AI — LiveKit WebRTC Voice Pipeline Worker.

Implements production patterns from LiveKit Voice AI Agents:
- Turn-taking with Silero VAD, preemptive generation, and false-interruption recovery
- Provider resilience via FallbackAdapter (STT, LLM, TTS)
- Real-time metrics & telemetry (UsageCollector, EOU/TTFT/TTFB latency broadcasting)
- Real-time news & updates tool (get_live_news) + web search + desktop/email/medical tools
- Optional MCP server integration (MCP_SERVER_URLS)
- Lesson 6 Consent & Escalations: AgentTask consent workflows and specialized agent handoffs
"""

from __future__ import annotations

import asyncio
import contextvars
from dataclasses import dataclass, field
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from typing import Any, Optional

# Ensure root is in path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(override=True)

import httpx
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AgentTask,
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
    room_io,
    stt,
    tts,
)
from livekit.plugins import openai, silero
from agent.local_voice import (
    LocalEdgeTTS,
    LocalPiperTTS,
    LocalWhisperSTT,
    _stt_model_size,
    is_strict_local_mode,
)
from agent.voice_telemetry import TurnTimer
from agent.prompts import SYSTEM_PROMPT
from agent.screening import screen_input, screen_output
from agent.voice import clean_spoken_text
from agent.tools import (
    calc,
    calendar,
    coding,
    docs,
    email,
    launcher,
    medical,
    memory_tools,
    search,
    tasks,
    whatsapp,
)

logger = logging.getLogger("nexus.livekit_worker")


# --------------------------------------------------------------------------- #
# Per-Room Session State & Real-Time SSE Event Broadcasting
# --------------------------------------------------------------------------- #

@dataclass
class LiveKitSessionState:
    room: Optional[Any] = None
    user_id: str = "guest"
    current_turn_tools: list[dict] = field(default_factory=list)
    last_user_transcript: str = ""
    launched_in_turn: set[str] = field(default_factory=set)


_LK_STATE: contextvars.ContextVar[Optional[LiveKitSessionState]] = contextvars.ContextVar("lk_session_state", default=None)
_BACKEND_HTTP_CLIENT: Optional[httpx.AsyncClient] = None


def _get_lk_state() -> LiveKitSessionState:
    state = _LK_STATE.get(None)
    if state is None:
        state = LiveKitSessionState()
        _LK_STATE.set(state)
    return state


def _is_room_connected(state: Optional[LiveKitSessionState] = None) -> bool:
    st = state or _get_lk_state()
    room = st.room
    return bool(
        room
        and getattr(room, "local_participant", None)
        and (not hasattr(room, "isconnected") or room.isconnected())
    )


def _get_backend_client() -> httpx.AsyncClient:
    """Return a shared non-SSL AsyncClient for localhost SSE updates without blocking the event loop."""
    global _BACKEND_HTTP_CLIENT
    if _BACKEND_HTTP_CLIENT is None or _BACKEND_HTTP_CLIENT.is_closed:
        _BACKEND_HTTP_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(1.0), verify=False)
    return _BACKEND_HTTP_CLIENT


async def _push_backend_update(event_type: str, data: dict) -> None:
    """Forward real-time telemetry, news, or state events to the FastAPI SSE bus."""
    port = os.environ.get("PORT", "8000")
    url = f"http://127.0.0.1:{port}/api/updates/publish"
    try:
        client = _get_backend_client()
        await client.post(url, json={"event_type": event_type, "data": data})
    except Exception:
        pass


async def _broadcast_client_action(action_type: str, data: dict) -> None:
    """Publish a real-time event to the WebRTC room data channel and SSE dashboard."""
    state = _get_lk_state()
    if _is_room_connected(state):
        try:
            payload = json.dumps({"type": action_type, **data}).encode("utf-8")
            await state.room.local_participant.publish_data(payload, reliable=True)
        except Exception as e:
            logger.debug(f"Could not publish data action to room: {e}")

    if action_type in {"METRICS_UPDATE", "AGENT_STATE", "NEWS_UPDATE", "ESCALATION_EVENT", "CONSENT_UPDATE"}:
        asyncio.create_task(_push_backend_update(action_type, data))


def _maybe_launch_app_from_speech(text: str) -> bool:
    """Detect explicit app launching intent directly from user speech transcript without false triggers."""
    if not text:
        return False
    state = _get_lk_state()
    if any(t.get("tool") == "open_app" for t in state.current_turn_tools):
        return True
    lower_t = text.lower().strip()

    has_launch_verb = bool(
        re.search(
            r"\b(?:open|launch|start|run|play|watch|listen|go\s+to|navigate|visit)\b",
            lower_t,
        )
    )
    if not has_launch_verb:
        return False

    target_app = None
    if re.search(r"\byoutube\b", lower_t) or (re.search(r"\bvideos?\b", lower_t) and any(w in lower_t for w in ["open", "play", "watch"])):
        target_app = "youtube"
    elif re.search(r"\bspotify\b", lower_t) or (re.search(r"\bmusic\b", lower_t) and any(w in lower_t for w in ["open", "play", "listen"])):
        target_app = "spotify"
    elif re.search(r"\bwhatsapp\b", lower_t) and not re.search(r"\b(?:message|text|send|chat\s+with)\b", lower_t):
        target_app = "whatsapp"
    elif re.search(r"\blinkedin\b", lower_t):
        target_app = "linkedin"
    elif re.search(r"\bgithub\b", lower_t):
        target_app = "github"
    elif re.search(r"\b(?:gmail|inbox)\b", lower_t):
        target_app = "gmail"
    elif re.search(r"\b(?:calculator|calc)\b", lower_t):
        target_app = "calculator"
    elif re.search(r"\bnotepad\b", lower_t):
        target_app = "notepad"
    elif re.search(r"\b(?:file\s+explorer|explorer)\b", lower_t):
        target_app = "explorer"

    if not target_app:
        return False

    if target_app in state.launched_in_turn:
        return True
    state.launched_in_turn.add(target_app)

    query = ""
    if target_app == "youtube":
        m_q = re.search(r'(?:search\s+for|search|play|watch|video\s+for|videos\s+for|address\s+for)\s+([^.]+)', text, re.IGNORECASE)
        if m_q:
            query = re.sub(r"\byoutube\b", "", m_q.group(1), flags=re.IGNORECASE).strip()
    elif target_app == "spotify":
        m_q = re.search(r'(?:play|search\s+for|search|music\s+by)\s+([^.]+)', text, re.IGNORECASE)
        if m_q:
            query = re.sub(r"\bspotify\b", "", m_q.group(1), flags=re.IGNORECASE).strip()

    try:
        room_live = _is_room_connected(state)
        res = launcher.open_app(name=target_app, query=query, launch_browser=(not room_live))
        state.current_turn_tools.append({
            "tool": "open_app",
            "args": {"name": target_app, "query": query},
            "result": res,
        })
        if res.get("url"):
            asyncio.create_task(_broadcast_client_action("OPEN_URL", {
                "url": res["url"],
                "target": res.get("target") or target_app.capitalize(),
            }))
        logger.info(f"Auto-launched {target_app} from user speech (query: '{query}')")
        return True
    except Exception as e:
        logger.warning(f"Error launching {target_app} from speech: {e}")
        return False


def _maybe_launch_app_from_assistant_reply(text: str) -> bool:
    """Detect if assistant claimed it opened an app but failed to invoke the function tool."""
    if not text:
        return False
    state = _get_lk_state()
    lower_t = text.lower().strip()
    if any(t.get("tool") == "open_app" for t in state.current_turn_tools):
        return False

    claim_open = any(p in lower_t for p in [
        "have opened", "i opened", "i have opened", "opened youtube", "opened spotify",
        "opening youtube", "opening spotify", "opening ", "launched "
    ])
    if not claim_open:
        return False

    for app in ["youtube", "spotify", "whatsapp", "linkedin", "github", "gmail", "calculator", "notepad"]:
        if re.search(rf"\b{re.escape(app)}\b", lower_t):
            if app in state.launched_in_turn:
                return True
            state.launched_in_turn.add(app)
            try:
                room_live = _is_room_connected(state)
                res = launcher.open_app(name=app, query="", launch_browser=(not room_live))
                state.current_turn_tools.append({
                    "tool": "open_app",
                    "args": {"name": app, "query": ""},
                    "result": res,
                })
                if res.get("url"):
                    asyncio.create_task(_broadcast_client_action("OPEN_URL", {
                        "url": res["url"],
                        "target": res.get("target") or app.capitalize(),
                    }))
                logger.info(f"Auto-launched {app} from assistant response claim")
                return True
            except Exception as e:
                logger.warning(f"Error launching {app} from assistant claim: {e}")
                return False
    return False


# --------------------------------------------------------------------------- #
# Tool Definitions for LiveKit Agents
# --------------------------------------------------------------------------- #

@llm.function_tool
async def get_live_news(topic: str = "top", max_results: int = 4) -> str:
    """Fetch real-time breaking news and category headlines with publication timestamps and sources."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(search.get_live_news, topic=topic, max_results=max_results)
        state.current_turn_tools.append({"tool": "get_live_news", "args": {"topic": topic, "max_results": max_results}, "result": res})
        await _broadcast_client_action("NEWS_UPDATE", {
            "topic": res.get("topic", topic),
            "fetched_at": res.get("fetched_at", ""),
            "news_items": res.get("news_items", []),
            "spoken": res.get("spoken", ""),
        })
        return res.get("spoken") or str(res)
    except Exception as e:
        return f"Error fetching live news: {e}"


@llm.function_tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search Google News and DuckDuckGo for live news, real-time facts, cricket scores, and current events."""
    state = _get_lk_state()
    clean_q = (query or "").strip().lower()
    greetings = {"hello", "hi", "hey", "let me take a look", "thank you", "thanks", "ok", "okay", "none", "alone", "who are you"}
    if not clean_q or clean_q in greetings:
        return "I am listening. What would you like to search for?"
    try:
        res = await asyncio.to_thread(search.web_search, query=query, max_results=max_results)
        state.current_turn_tools.append({"tool": "web_search", "args": {"query": query, "max_results": max_results}, "result": res})
        if any(k in clean_q for k in ["news", "headline", "breaking", "score", "update"]):
            await _broadcast_client_action("NEWS_UPDATE", {
                "topic": query,
                "news_items": res.get("results", []),
                "spoken": res.get("spoken", ""),
            })
        return res.get("spoken") or str(res)
    except Exception as e:
        return f"Error searching the web: {e}"


@llm.function_tool
async def calculator(expression: str) -> str:
    """Safely calculate mathematical equations, percentages, powers, or arithmetic expressions."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(calc.calculator, expression=expression)
        state.current_turn_tools.append({"tool": "calculator", "args": {"expression": expression}, "result": res})
        return res.get("spoken") or str(res.get("result"))
    except Exception as e:
        return f"Error calculating: {e}"


@llm.function_tool
async def run_python_code(code: str) -> str:
    """Execute Python code in an isolated REPL to test algorithms, compute logic, or verify scripts."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(coding.run_python_code, code=code)
        state.current_turn_tools.append({"tool": "run_python_code", "args": {"code": code}, "result": res})
        return res.get("spoken") or (res.get("output") or "Code executed with no output.")
    except Exception as e:
        return f"Error executing Python code: {e}"


@llm.function_tool
async def get_current_time(timezone: str = "Asia/Kolkata") -> str:
    """Get the current time, date, day of week, and timezone."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(search.get_current_time, timezone=timezone)
        state.current_turn_tools.append({"tool": "get_current_time", "args": {"timezone": timezone}, "result": res})
        return res.get("spoken") or f"Current time is {res.get('iso')} ({res.get('timezone')})."
    except Exception as e:
        return f"Error getting current time: {e}"


@llm.function_tool
async def open_app(name: str, query: str = "") -> str:
    """Open desktop applications (Calculator, Notepad, Explorer) or websites (YouTube, WhatsApp, LinkedIn, Spotify, GitHub, Gmail)."""
    state = _get_lk_state()
    try:
        room_live = _is_room_connected(state)
        res = await asyncio.to_thread(launcher.open_app, name=name, query=query, launch_browser=(not room_live))
        state.current_turn_tools.append({"tool": "open_app", "args": {"name": name, "query": query}, "result": res})
        state.launched_in_turn.add((name or "").strip().lower())
        if res.get("url"):
            await _broadcast_client_action("OPEN_URL", {"url": res["url"], "target": res.get("target")})
        return res.get("spoken") or f"Opening {name}."
    except Exception as e:
        return f"Error opening application {name}: {e}"


@llm.function_tool
async def send_whatsapp_message(contact_name: str, message: str = "") -> str:
    """Search for a contact in WhatsApp Web or Desktop, open their chat, and send a message."""
    state = _get_lk_state()
    clean_c = (contact_name or "").strip()
    if not clean_c or clean_c.lower() in {"hello", "none", "me"}:
        return "Please specify the contact name you want to message on WhatsApp."
    try:
        room_live = _is_room_connected(state)
        res = await asyncio.to_thread(whatsapp.send_whatsapp_message, contact_name=contact_name, message=message, launch_browser=(not room_live))
        state.current_turn_tools.append({"tool": "send_whatsapp_message", "args": {"contact_name": contact_name, "message": message}, "result": res})
        if res.get("url"):
            await _broadcast_client_action("OPEN_URL", {"url": res["url"], "target": "WhatsApp"})
        return res.get("spoken") or f"Sent WhatsApp message to {contact_name}."
    except Exception as e:
        return f"Error sending WhatsApp message: {e}"


def _clean_optional_arg(val: str) -> str:
    """Normalize stringified None/null placeholders from small LLMs into empty strings."""
    cleaned = (val or "").strip()
    if cleaned.lower() in {"none", "null", "n/a", "na", "undefined", "unknown"}:
        return ""
    return cleaned


def _get_active_user_name_fast(user_id: Optional[str] = None) -> str:
    """Resolve user display name from SQLite directly without importing FastAPI."""
    try:
        from db.models import db_get_user_by_id, db_get_user_oauth
        if user_id and str(user_id).strip() not in ("guest", "None", ""):
            u = db_get_user_by_id(user_id)
            if u and u.get("username"):
                return str(u["username"]).capitalize()
        oauth = db_get_user_oauth(user_id=user_id)
        if oauth and oauth.get("email"):
            return email._infer_recipient_name(oauth["email"]) or "User"
    except Exception:
        pass
    return os.environ.get("USER_NAME", "").strip() or "User"


@llm.function_tool
async def send_email(to: str, description: str, recipient_name: str = "", sender_email: str = "", sender_name: str = "") -> str:
    """Compose and send emails to a single recipient, multiple recipients, or bulk contacts from contacts.csv."""
    state = _get_lk_state()
    raw_to = _clean_optional_arg(to)
    recipient_name = _clean_optional_arg(recipient_name)
    sender_email = _clean_optional_arg(sender_email)
    sender_name = _clean_optional_arg(sender_name)

    norm_to = email.normalize_spoken_email(raw_to) if raw_to else ""
    placeholder_emails = {
        "recipient@example.com", "john.doe@example.com", "jane.doe@example.com",
        "example@example.com", "user@example.com", "test@example.com",
    }
    if (
        not norm_to
        or "@" not in norm_to
        or norm_to.lower() in placeholder_emails
        or recipient_name.lower() in {"john doe", "jane doe"}
    ):
        return "To send an email, please tell me the recipient's valid email address and what you would like to say."

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", norm_to) and ".csv" not in norm_to.lower():
        return f"I could not verify the email address '{raw_to}'. Please repeat or spell out the exact recipient email address."

    try:
        eff_sender = sender_name or _get_active_user_name_fast(state.user_id)
        res = await asyncio.to_thread(
            email.send_email,
            to=norm_to,
            description=description,
            recipient_name=recipient_name,
            user_id=state.user_id,
            sender_email=sender_email or None,
            sender_name=eff_sender,
        )
        state.current_turn_tools.append({
            "tool": "send_email",
            "args": {"to": norm_to, "description": description, "recipient_name": recipient_name, "sender_name": eff_sender},
            "result": res,
        })
        if res.get("success"):
            await _broadcast_client_action("EMAIL_SENT", {
                "to": norm_to,
                "subject": res.get("subject", ""),
                "sender": res.get("from", ""),
                "sender_name": eff_sender,
                "provider": res.get("provider", "email"),
            })
        return res.get("spoken") or f"Email sent to {norm_to}."
    except Exception as e:
        return f"Error delivering email: {e}"


@llm.function_tool
async def medical_search(medicine_name: str, topic: str = "all", user_query: str = "") -> str:
    """Look up comprehensive, verified medical information about any medicine, drug, brand, or salt."""
    state = _get_lk_state()
    clean_med = (medicine_name or "").strip().lower()
    if not clean_med or clean_med in {"hello", "hi", "none"}:
        return "Please name the medicine or salt you would like information on."
    try:
        eff_query = (user_query or state.last_user_transcript or "").strip() or None
        res = await asyncio.to_thread(medical.medical_search, medicine_name=medicine_name, topic=topic, user_query=eff_query)
        state.current_turn_tools.append({"tool": "medical_search", "args": {"medicine_name": medicine_name, "topic": topic}, "result": res})
        return res.get("spoken") or f"Retrieved information for {medicine_name}."
    except Exception as e:
        return f"Error looking up medicine {medicine_name}: {e}"


@llm.function_tool
async def add_task(title: str, priority: str = "medium", due_date: str = "") -> str:
    """Add a new task or to-do item."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(tasks.add_task, title=title, priority=priority, due_date=due_date or None, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "add_task", "args": {"title": title, "priority": priority}, "result": res})
        return res.get("spoken") or f"Added task {title}."
    except Exception as e:
        return f"Error adding task: {e}"


@llm.function_tool
async def list_tasks(status: str = "pending") -> str:
    """List tasks filtered by status ('pending', 'completed', or 'all')."""
    state = _get_lk_state()
    try:
        eff_status = None if str(status).lower().strip() == "all" else status
        res = await asyncio.to_thread(tasks.list_tasks, status=eff_status, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "list_tasks", "args": {"status": status}, "result": res})
        return res.get("spoken") or "Listed tasks."
    except Exception as e:
        return f"Error listing tasks: {e}"


@llm.function_tool
async def complete_task(task_id: str) -> str:
    """Mark a task completed by ID or title keyword."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(tasks.complete_task, task_id=task_id, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "complete_task", "args": {"task_id": task_id}, "result": res})
        return res.get("spoken") or f"Completed task {task_id}."
    except Exception as e:
        return f"Error completing task: {e}"


@llm.function_tool
async def delete_task(task_id: str) -> str:
    """Delete a task permanently by ID or title."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(tasks.delete_task, task_id=task_id, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "delete_task", "args": {"task_id": task_id}, "result": res})
        return res.get("spoken") or f"Deleted task {task_id}."
    except Exception as e:
        return f"Error deleting task: {e}"


@llm.function_tool
async def list_events(date: str = "today") -> str:
    """List calendar events for a date ('today', 'tomorrow', or YYYY-MM-DD)."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(calendar.list_events, date=date, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "list_events", "args": {"date": date}, "result": res})
        return res.get("spoken") or "Checked calendar events."
    except Exception as e:
        return f"Error listing events: {e}"


@llm.function_tool
async def find_free_slot(duration_minutes: int = 30, window: str = "today") -> str:
    """Find an open meeting slot on the calendar without conflicts."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(calendar.find_free_slot, duration_minutes=duration_minutes, window=window, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "find_free_slot", "args": {"duration_minutes": duration_minutes, "window": window}, "result": res})
        return res.get("spoken") or "Checked free slots."
    except Exception as e:
        return f"Error finding free slot: {e}"


@llm.function_tool
async def create_event(title: str, start: str, end: str = "") -> str:
    """Schedule a calendar event."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(calendar.create_event, title=title, start=start, end=end or None, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "create_event", "args": {"title": title, "start": start, "end": end}, "result": res})
        return res.get("spoken") or f"Scheduled {title}."
    except Exception as e:
        return f"Error scheduling event: {e}"


@llm.function_tool
async def search_emails(query: str = "", max_results: int = 5) -> str:
    """Search inbox emails by keyword or sender name."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(email.search_email, query=query, max_results=max_results)
        state.current_turn_tools.append({"tool": "search_emails", "args": {"query": query, "max_results": max_results}, "result": res})
        return res.get("spoken") or "No matching emails found."
    except Exception as e:
        return f"Error searching emails: {e}"


@llm.function_tool
async def summarize_email(id: str = "") -> str:
    """Summarize an email message by ID or sender keyword."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(email.summarize_email, id=id or None)
        state.current_turn_tools.append({"tool": "summarize_email", "args": {"id": id}, "result": res})
        return res.get("spoken") or "Could not find email."
    except Exception as e:
        return f"Error summarizing email: {e}"


@llm.function_tool
async def draft_reply(id: str = "", instructions: str = "") -> str:
    """Draft an email reply without sending it."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(email.draft_reply, id=id or None, instructions=instructions or None)
        state.current_turn_tools.append({"tool": "draft_reply", "args": {"id": id, "instructions": instructions}, "result": res})
        return res.get("spoken") or "Created draft reply."
    except Exception as e:
        return f"Error drafting reply: {e}"


@llm.function_tool
async def remember(fact: str, category: str = "general") -> str:
    """Store a personal fact or user preference in long-term memory."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(memory_tools.remember, fact=fact, category=category, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "remember", "args": {"fact": fact, "category": category}, "result": res})
        return res.get("spoken") or f"Remembered: {fact}."
    except Exception as e:
        return f"Error remembering fact: {e}"


@llm.function_tool
async def forget(fact: str) -> str:
    """Remove a stored fact or preference from memory."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(memory_tools.forget, fact=fact, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "forget", "args": {"fact": fact}, "result": res})
        return res.get("spoken") or f"Forgot: {fact}."
    except Exception as e:
        return f"Error forgetting fact: {e}"


@llm.function_tool
async def search_my_docs(query: str) -> str:
    """Search personal indexed documents and local notes."""
    state = _get_lk_state()
    try:
        res = await asyncio.to_thread(docs.search_my_docs, query=query, user_id=state.user_id)
        state.current_turn_tools.append({"tool": "search_my_docs", "args": {"query": query}, "result": res})
        return res.get("spoken") or "No matching documents found."
    except Exception as e:
        return f"Error searching docs: {e}"


LIVEKIT_TOOLS = [
    get_live_news,
    web_search,
    calculator,
    medical_search,
    run_python_code,
    get_current_time,
    open_app,
    send_whatsapp_message,
    send_email,
    search_emails,
    summarize_email,
    draft_reply,
    add_task,
    list_tasks,
    complete_task,
    delete_task,
    list_events,
    find_free_slot,
    create_event,
    remember,
    forget,
    search_my_docs,
]


# --------------------------------------------------------------------------- #
# Lesson 6: Consent Tasks & Specialized Agent Handoffs / Escalations
# --------------------------------------------------------------------------- #

class CollectConsentTask(AgentTask[bool]):
    """Isolated AgentTask that collects explicit verbal recording/session consent before proceeding."""

    def __init__(self, chat_ctx: Optional[llm.ChatContext] = None):
        super().__init__(
            instructions=(
                "Ask the user for consent to process and log this voice session for quality and continuity. "
                "Accept a clear yes or no answer politely."
            ),
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="Briefly greet the user and ask if they consent to logging this voice session. Keep it one short sentence."
        )

    @llm.function_tool
    async def consent_given(self) -> None:
        """Call this when the user gives consent."""
        await _broadcast_client_action("CONSENT_UPDATE", {"consent": True, "scope": "session"})
        self.complete(True)

    @llm.function_tool
    async def consent_denied(self) -> None:
        """Call this when the user declines consent."""
        await _broadcast_client_action("CONSENT_UPDATE", {"consent": False, "scope": "session"})
        self.complete(False)


class ActionConsentTask(AgentTask[bool]):
    """Isolated AgentTask for verbal confirmation before sensitive actions (emails, escalations)."""

    def __init__(self, action_summary: str, chat_ctx: Optional[llm.ChatContext] = None):
        self._action_summary = action_summary
        super().__init__(
            instructions=(
                f"Ask the user to verbally confirm this action: {action_summary}. "
                "Call confirm_action if they say yes, or decline_action if they say no."
            ),
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions=f"Ask clearly in one sentence whether the user confirms: {self._action_summary}."
        )

    @llm.function_tool
    async def confirm_action(self) -> None:
        """Call when the user approves the action."""
        self.complete(True)

    @llm.function_tool
    async def decline_action(self) -> None:
        """Call when the user cancels or declines the action."""
        self.complete(False)


class NewsBriefingAgent(Agent):
    """Specialized real-time news anchor agent delivering breaking updates and topic briefings."""

    def __init__(self, chat_ctx: Optional[llm.ChatContext] = None, topic: str = "top"):
        self._topic = topic
        super().__init__(
            instructions=(
                f"{_get_voice_instructions()}\n\n"
                "You are now acting as the Live News & Updates Anchor. "
                "Always use get_live_news for headlines and category briefings (world, india, technology, business, sports, science, health). "
                "Deliver crisp, timestamped updates and offer to switch topics or return to the main assistant."
            ),
            tools=[get_live_news, web_search, get_current_time],
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await _broadcast_client_action("AGENT_STATE", {"state": "news_anchor", "topic": self._topic})
        await self.session.generate_reply(
            instructions=f"Fetch and deliver the latest {self._topic} news briefing right now using get_live_news."
        )

    @llm.function_tool
    async def return_to_assistant(self):
        """Hand control back to the primary Nexus assistant when the user finishes with news."""
        return NexusVoiceAgent(chat_ctx=self.chat_ctx), "Returning you to your main Nexus assistant."


class EscalationSpecialistAgent(Agent):
    """Escalation & support handoff agent that captures unresolved issues and logs escalation records."""

    def __init__(self, chat_ctx: Optional[llm.ChatContext] = None, reason: str = ""):
        self._reason = reason
        super().__init__(
            instructions=(
                "You are a Senior Escalation Specialist for Nexus AI. "
                "Acknowledge the user's request empathetically, summarize what happened from the conversation, "
                "log an escalation ticket with log_escalation_ticket if needed, or return to the main assistant."
            ),
            tools=[get_live_news, web_search, get_current_time],
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        state = _get_lk_state()
        await _broadcast_client_action("ESCALATION_EVENT", {
            "status": "escalated",
            "reason": self._reason or "User requested specialist escalation",
            "user_id": state.user_id,
        })
        await self.session.generate_reply(
            instructions="Reassure the user that a senior specialist has taken over with full context, and ask how you can resolve their issue."
        )

    @llm.function_tool
    async def log_escalation_ticket(self, summary: str, priority: str = "high") -> str:
        """Record an escalation ticket in the local database and notify the dashboard.

        Args:
            summary: Concise summary of the issue to escalate.
            priority: Priority level ('normal', 'high', 'urgent').
        """
        state = _get_lk_state()
        try:
            from db.models import db_add_task
            res = db_add_task(title=f"[Escalation - {priority.upper()}] {summary}", priority=priority, user_id=state.user_id)
            await _broadcast_client_action("ESCALATION_EVENT", {
                "status": "ticket_logged",
                "task_id": res.get("id", ""),
                "summary": summary,
                "priority": priority,
            })
            return f"Logged escalation ticket with {priority} priority: {summary}."
        except Exception as e:
            return f"Could not log escalation ticket: {e}"

    @llm.function_tool
    async def return_to_assistant(self):
        """Return control back to the primary Nexus assistant."""
        return NexusVoiceAgent(chat_ctx=self.chat_ctx), "Transferring you back to Nexus AI."


def _get_voice_instructions() -> str:
    """Return lean voice-optimized instructions tuned for Ollama or full prompt for cloud LLMs."""
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    if "11434" in base_url or not os.environ.get("OPENAI_API_KEY", "").strip().startswith("sk-"):
        return (
            "You are Nexus AI, a fast, natural voice assistant. "
            "ALWAYS reply in English ONLY in 1 to 2 crisp spoken sentences. "
            "NEVER use markdown, bullet lists, placeholder brackets like [Your Name], email draft templates, or raw JSON. "
            "For simple greetings like 'hello', 'hi', or 'thanks', reply warmly in one short sentence WITHOUT calling any tool. "
            "NEVER invent fake or placeholder email recipients like John Doe or recipient@example.com. "
            "If the user wants to send an email without giving a real recipient address and message yet, simply ask who to send it to and what to say without calling send_email. "
            "Only call tools when you have real user parameters: get_live_news for breaking/category news, "
            "web_search for live facts or cricket scores, calculator for math, medical_search for medicines, "
            "open_app for YouTube/apps, send_whatsapp_message for WhatsApp, send_email for email, "
            "get_current_time for time, run_python_code for Python."
        )
    return SYSTEM_PROMPT


class NexusVoiceAgent(Agent):
    """Primary voice-first Nexus AI agent with full tool suite and specialist handoffs."""

    def __init__(self, chat_ctx: Optional[llm.ChatContext] = None):
        super().__init__(
            instructions=_get_voice_instructions(),
            tools=LIVEKIT_TOOLS,
            chat_ctx=chat_ctx,
        )

    @llm.function_tool
    async def handoff_to_news_anchor(self, topic: str = "top"):
        """Transfer to the specialized Live News Anchor for breaking news briefings and real-time updates.

        Args:
            topic: News category ('top', 'world', 'india', 'technology', 'business', 'sports', 'science', 'health').
        """
        return NewsBriefingAgent(chat_ctx=self.chat_ctx, topic=topic), f"Connecting you to live {topic} news updates."

    @llm.function_tool
    async def escalate_to_specialist(self, reason: str = "User requested specialist assistance"):
        """Escalate the conversation to a senior specialist when the user asks for human/specialist help or hits a blocker.

        Args:
            reason: Brief summary of why the user needs escalation.
        """
        return EscalationSpecialistAgent(chat_ctx=self.chat_ctx, reason=reason), "Connecting you to an escalation specialist now."


# --------------------------------------------------------------------------- #
# Pipeline Builder: Fallbacks, Turn Detection, Metrics & MCP
# --------------------------------------------------------------------------- #

def _env_float(name: str, default: float) -> float:
    """Parse a positive float from environment variables with safe fallback."""
    try:
        return float(os.environ.get(name, str(default)).strip() or default)
    except ValueError:
        return default


def _load_silero_vad() -> silero.VAD:
    """Load Silero VAD using env-tunable thresholds matching the verified baseline."""
    return silero.VAD.load(
        activation_threshold=_env_float("VAD_ACTIVATION_THRESHOLD", 0.55),
        min_speech_duration=_env_float("VAD_MIN_SPEECH_DURATION", 0.08),
        min_silence_duration=_env_float("VAD_MIN_SILENCE_DURATION", 0.65),
    )


def _build_resilient_engines(vad_detector: silero.VAD) -> tuple[Any, Any, Any]:
    """Construct STT, LLM, and TTS pipelines with FallbackAdapter redundancy where secondary providers exist."""
    local_base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").strip() or "http://localhost:11434/v1"
    local_model = os.environ.get("OPENAI_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"
    fallback_model = os.environ.get("FALLBACK_LLM_MODEL", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip() or "ollama"
    whisper_size = _stt_model_size()
    strict_local = is_strict_local_mode()

    local_stt = stt.StreamAdapter(stt=LocalWhisperSTT(model_size=whisper_size), vad=vad_detector)
    local_piper = LocalPiperTTS()
    if strict_local:
        if local_piper.is_available:
            local_tts_chunked = local_piper
        else:
            logger.warning("STRICT_LOCAL_MODE enabled and Piper model not found; using Edge-TTS disabled fallback.")
            local_tts_chunked = local_piper
    else:
        local_edge = LocalEdgeTTS(voice="en-US-ChristopherNeural")
        if local_piper.is_available:
            local_tts_chunked = tts.FallbackAdapter(
                [local_piper, local_edge],
                max_retry_per_tts=1,
                sample_rate=local_piper.sample_rate,
            )
        else:
            local_tts_chunked = local_edge
    local_tts_primary = tts.StreamAdapter(tts=local_tts_chunked)

    if not strict_local and api_key.startswith("sk-"):
        stt_engine = stt.FallbackAdapter([openai.STT(api_key=api_key), local_stt], vad=vad_detector)
        tts_engine = tts.FallbackAdapter([
            openai.TTS(voice=os.environ.get("OPENAI_TTS_VOICE", "alloy"), api_key=api_key),
            local_tts_primary,
        ])
    else:
        stt_engine = local_stt
        tts_engine = local_tts_primary

    def _build_ollama_extra_body(model_name: str) -> dict[str, Any]:
        body: dict[str, Any] = {"options": {"num_ctx": 4096}, "keep_alive": "30m"}
        if "qwen3" in model_name.lower():
            body["think"] = False
        return body

    llm_kwargs: dict[str, Any] = {
        "model": local_model,
        "base_url": local_base,
        "api_key": api_key,
        "temperature": 0.2,
        "max_completion_tokens": 220,
    }
    if "11434" in local_base:
        llm_kwargs["extra_body"] = _build_ollama_extra_body(local_model)

    primary_llm = openai.LLM(**llm_kwargs)
    llm_candidates = [primary_llm]
    if fallback_model and fallback_model != local_model:
        fb_kwargs = {**llm_kwargs, "model": fallback_model}
        if "11434" in local_base:
            fb_kwargs["extra_body"] = _build_ollama_extra_body(fallback_model)
        llm_candidates.append(openai.LLM(**fb_kwargs))
    elif api_key.startswith("sk-") and local_model != "gpt-4o-mini":
        llm_candidates.append(openai.LLM(model="gpt-4o-mini", api_key=api_key))

    llm_engine = (
        llm.FallbackAdapter(llm_candidates, attempt_timeout=20.0, max_retry_per_llm=1)
        if len(llm_candidates) > 1
        else primary_llm
    )
    return stt_engine, llm_engine, tts_engine


def _load_optional_mcp_servers() -> list[Any]:
    """Load optional MCP HTTP servers defined in MCP_SERVER_URLS when livekit-agents[mcp] is installed."""
    raw_urls = os.environ.get("MCP_SERVER_URLS", "").strip()
    if not raw_urls:
        return []
    try:
        from livekit.agents import mcp
        servers = []
        for u in [x.strip() for x in raw_urls.split(",") if x.strip()]:
            servers.append(mcp.MCPServerHTTP(url=u))
        return servers
    except Exception as exc:
        logger.warning(f"MCP servers configured but could not load MCP integration: {exc}")
        return []


# --------------------------------------------------------------------------- #
# LiveKit Voice Pipeline Entrypoint
# --------------------------------------------------------------------------- #

async def entrypoint(ctx: JobContext):
    """LiveKit agent worker entrypoint for WebRTC audio rooms."""
    lk_state = LiveKitSessionState(room=ctx.room)
    state_tok = _LK_STATE.set(lk_state)
    logger.info(f"Connecting to LiveKit room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the browser user to connect into the room
    logger.info("Waiting for user participant to connect...")
    try:
        participant = await ctx.wait_for_participant()
    except Exception as wait_err:
        logger.info(f"Room closed before participant joined ({ctx.room.name}): {wait_err}")
        _LK_STATE.reset(state_tok)
        return
    logger.info(f"Participant connected: {participant.identity} ({participant.name or 'User'})")

    # Resolve bound user_id for OAuth credentials and tools
    user_id = "guest"
    if participant.metadata:
        try:
            meta = json.loads(participant.metadata)
            if meta.get("user_id"):
                user_id = str(meta["user_id"])
        except Exception:
            pass
    if user_id == "guest" and participant.identity:
        if participant.identity.startswith("user-"):
            user_id = participant.identity.replace("user-", "", 1)
        elif not participant.identity.startswith("guest-"):
            user_id = participant.identity

    lk_state.user_id = user_id
    logger.info(f"LiveKit session bound to user_id: {lk_state.user_id}")

    vad_detector = ctx.proc.userdata.get("vad") or _load_silero_vad()
    stt_engine, llm_engine, tts_engine = _build_resilient_engines(vad_detector)
    mcp_servers = _load_optional_mcp_servers()

    session_kwargs: dict[str, Any] = {
        "vad": vad_detector,
        "stt": stt_engine,
        "llm": llm_engine,
        "tts": tts_engine,
        "turn_detection": "vad",
        "preemptive_generation": False,
        "min_endpointing_delay": _env_float("MIN_ENDPOINTING_DELAY", 0.55),
        "max_endpointing_delay": _env_float("MAX_ENDPOINTING_DELAY", 1.5),
        "min_interruption_duration": _env_float("MIN_INTERRUPTION_DURATION", 0.65),
        "min_interruption_words": int(_env_float("MIN_INTERRUPTION_WORDS", 2)),
        "resume_false_interruption": False,
        "use_tts_aligned_transcript": False,
        "aec_warmup_duration": _env_float("AEC_WARMUP_DURATION", 1.5),
        "allow_interruptions": _env_flag("ALLOW_INTERRUPTIONS", default=True),
    }
    if mcp_servers:
        session_kwargs["mcp_servers"] = mcp_servers

    session = AgentSession(**session_kwargs)
    usage_collector = metrics.UsageCollector()
    turns_by_speech_id: dict[str, TurnTimer] = {}
    turn_state: dict[str, Optional[TurnTimer]] = {"pending": None}

    def _get_or_bind_turn(speech_id: Optional[str]) -> TurnTimer:
        if speech_id:
            existing = turns_by_speech_id.get(speech_id)
            if existing is not None:
                return existing
            pending = turn_state.get("pending")
            if pending is not None and not pending.speech_id:
                pending.speech_id = speech_id
                pending.turn_id = speech_id[:8]
                turns_by_speech_id[speech_id] = pending
                turn_state["pending"] = None
            else:
                # Flush unrecorded previous turn before starting a new speech_id turn
                if pending is not None and not pending.recorded:
                    pending.record(extra={"room": ctx.room.name, "user_id": lk_state.user_id})
                turns_by_speech_id[speech_id] = TurnTimer(speech_id=speech_id)
                turn_state["pending"] = None
            if len(turns_by_speech_id) > 25:
                oldest_key = next(iter(turns_by_speech_id))
                old_turn = turns_by_speech_id.pop(oldest_key)
                if not old_turn.recorded:
                    old_turn.record(extra={"room": ctx.room.name, "user_id": lk_state.user_id})
            return turns_by_speech_id[speech_id]

        if turn_state.get("pending") is None:
            turn_state["pending"] = TurnTimer()
        return turn_state["pending"]  # type: ignore[return-value]

    @session.on("metrics_collected")
    def on_metrics_collected(ev):
        m = getattr(ev, "metrics", None)
        if m is None:
            return
        cls_name = type(m).__name__
        if cls_name == "VADMetrics":
            return
        try:
            usage_collector.collect(m)
            metrics.log_metrics(m)
        except Exception:
            pass

        speech_id = getattr(m, "speech_id", None) or None
        turn = _get_or_bind_turn(speech_id)

        if cls_name == "STTMetrics":
            stt_dur = float(getattr(m, "duration", 0.0) or 0.0)
            turn.set_stage_ms("stt_ms", stt_dur * 1000.0)
            turn.mark("stt_final")
            return
        elif cls_name == "EOUMetrics":
            turn.mark("endpoint")
            eou_del = float(getattr(m, "end_of_utterance_delay", 0.0) or 0.0)
            tx_del = float(getattr(m, "transcription_delay", 0.0) or 0.0)
            turn.set_stage_ms("eou_ms", eou_del * 1000.0)
            if "stt_ms" not in turn.metrics_ms and tx_del > 0:
                turn.set_stage_ms("stt_ms", tx_del * 1000.0)
        elif cls_name == "LLMMetrics":
            if getattr(m, "cancelled", False):
                turn.interrupted = True
                return
            turn.mark("llm_first_token")
            turn.set_stage_ms("llm_ttft_ms", float(getattr(m, "ttft", 0.0) or 0.0) * 1000.0)
        elif cls_name == "TTSMetrics":
            if getattr(m, "cancelled", False):
                turn.interrupted = True
                return
            turn.mark("tts_first_audio")
            turn.set_stage_ms("tts_ttfb_ms", float(getattr(m, "ttfb", 0.0) or 0.0) * 1000.0)
            turn.record(extra={"room": ctx.room.name, "user_id": lk_state.user_id})

        snap = turn.snapshot()
        asyncio.create_task(_broadcast_client_action("METRICS_UPDATE", {
            "metric_type": cls_name,
            "turn_id": snap["turn_id"],
            "speech_id": snap["speech_id"],
            "eou_ms": snap["eou_ms"],
            "stt_ms": snap["stt_ms"],
            "llm_ttft_ms": snap["llm_ttft_ms"],
            "tts_ttfb_ms": snap["tts_ttfb_ms"],
            "turn_latency_ms": snap["server_ttfa_ms"],
            "room": ctx.room.name,
        }))

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev):
        new_state = str(getattr(ev, "new_state", ""))
        old_state = str(getattr(ev, "old_state", ""))
        asyncio.create_task(_broadcast_client_action("AGENT_STATE", {
            "state": new_state,
            "previous_state": old_state,
            "room": ctx.room.name,
        }))

    @session.on("user_input_transcribed")
    def on_user_transcribed(ev):
        if not getattr(ev, "is_final", False):
            return
        transcript = (getattr(ev, "transcript", "") or "").strip()
        if not transcript:
            return
        lk_state.launched_in_turn.clear()
        in_res = screen_input(transcript, user_id=lk_state.user_id)
        lk_state.last_user_transcript = in_res.sanitized_text or transcript
        if in_res.passed:
            _maybe_launch_app_from_speech(lk_state.last_user_transcript)

    @session.on("conversation_item_added")
    def on_conversation_item_added(ev):
        item = getattr(ev, "item", None)
        if not item:
            return
        role = getattr(item, "role", "")
        if role not in ("user", "assistant"):
            return
        raw_text = getattr(item, "raw_text_content", None) or getattr(item, "text_content", None) or getattr(item, "text", None) or ""
        if isinstance(raw_text, (list, tuple)):
            raw_text = " ".join(str(x) for x in raw_text)
        text = str(raw_text).strip()
        if not text:
            return

        if role == "user":
            in_res = screen_input(text, user_id=lk_state.user_id)
            clean_user_text = in_res.sanitized_text or text
            if clean_user_text != lk_state.last_user_transcript:
                lk_state.launched_in_turn.clear()
                lk_state.last_user_transcript = clean_user_text
                if in_res.passed:
                    _maybe_launch_app_from_speech(clean_user_text)
            asyncio.create_task(_broadcast_client_action("CHAT_MESSAGE", {
                "role": "user",
                "text": clean_user_text,
            }))
        elif role == "assistant":
            tools_snapshot = list(lk_state.current_turn_tools)
            screened = screen_output(text, tool_calls=tools_snapshot)
            spoken_text = clean_spoken_text(screened.sanitized_text or text) or text
            _maybe_launch_app_from_assistant_reply(spoken_text)
            tools_to_send = list(lk_state.current_turn_tools)
            lk_state.current_turn_tools.clear()
            asyncio.create_task(_broadcast_client_action("CHAT_MESSAGE", {
                "role": "assistant",
                "text": spoken_text,
                "tool_calls": tools_to_send,
            }))
            async def _persist_lk_turn(u_id: str, sess: str, u_msg: str, a_msg: str, t_list: list) -> None:
                try:
                    from db.models import db_save_chat_turn
                    await asyncio.to_thread(
                        db_save_chat_turn,
                        user_id=u_id,
                        session_id=sess,
                        user_message=u_msg,
                        spoken_reply=a_msg,
                        tool_calls=t_list,
                    )
                except Exception as db_err:
                    logger.warning(f"Error saving LiveKit turn to SQLite: {db_err}")

            asyncio.create_task(_persist_lk_turn(
                lk_state.user_id,
                ctx.room.name,
                lk_state.last_user_transcript or "(Voice query)",
                spoken_text,
                tools_to_send,
            ))

    async def _cleanup_room_session():
        try:
            pending = turn_state.get("pending")
            if pending is not None and not pending.recorded:
                pending.record(extra={"room": ctx.room.name, "user_id": lk_state.user_id})
            for t in turns_by_speech_id.values():
                if not t.recorded:
                    t.record(extra={"room": ctx.room.name, "user_id": lk_state.user_id})
            summary = usage_collector.get_summary()
            logger.info(f"Session usage summary for {ctx.room.name}: {summary}")
        except Exception:
            pass
        finally:
            try:
                _LK_STATE.reset(state_tok)
            except Exception:
                pass

    ctx.add_shutdown_callback(_cleanup_room_session)

    agent = NexusVoiceAgent()
    await session.start(
        agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(close_on_disconnect=False),
    )

    if os.environ.get("REQUIRE_VOICE_CONSENT", "false").lower() in {"1", "true", "yes"}:
        consent_ok = await CollectConsentTask(chat_ctx=agent.chat_ctx)
        if not consent_ok:
            await session.generate_reply(
                instructions="Politely acknowledge that session logging was declined and let the user know you can still assist them without saving logs."
            )

    logger.info("AgentSession started with local VAD, FallbackAdapter, metrics, and handoffs")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def prewarm_ollama() -> Optional[float]:
    """Send a minimal generate ping so Ollama loads qwen2.5:1.5b with keep_alive prior to Turn 1."""
    base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").strip()
    if "11434" not in base:
        return None
    import urllib.request

    model_name = os.environ.get("OPENAI_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"
    keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"
    try:
        num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "4096").strip() or "4096")
    except ValueError:
        num_ctx = 4096

    url = f"{base.rstrip('/').removesuffix('/v1')}/api/generate"
    payload = json.dumps({
        "model": model_name,
        "prompt": "Hi",
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"num_ctx": num_ctx, "num_predict": 1},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        resp.read()
    return round((time.perf_counter() - t0) * 1000.0, 1)


def prewarm(proc: JobProcess):
    """Prewarm the single configured local STT, TTS, and VAD models on CPU (plus optional env-gated warmups)."""
    try:
        proc.userdata["vad"] = _load_silero_vad()
        if not is_strict_local_mode():
            import edge_tts
            import edge_tts.communicate
        from agent.local_voice import _get_piper_voice, _get_whisper_model, prewarm_stt_decode
        whisper_size = _stt_model_size()
        _get_whisper_model(whisper_size)
        _get_piper_voice()
        if _env_flag("PREWARM_STT_DECODE", default=False):
            ms_stt = prewarm_stt_decode(whisper_size, duration_s=1.0)
            logger.info(f"Prewarmed STT decode ({whisper_size}) in {ms_stt} ms.")
        if _env_flag("PREWARM_OLLAMA", default=False):
            ms_llm = prewarm_ollama()
            logger.info(f"Prewarmed Ollama resident model in {ms_llm} ms.")
        logger.info(f"Prewarmed Silero VAD, Piper TTS, and faster-whisper ({whisper_size}) successfully.")
    except Exception as e:
        logger.warning(f"LiveKit prewarm notice: {e}")


server_options = WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm)
