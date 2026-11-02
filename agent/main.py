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
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Header
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
from agent.prompts import SYSTEM_PROMPT
from agent.confirm import requires_confirmation, format_read_back, is_confirmed
from agent.memory import get_memory_context
from agent.tools import TOOLS_REGISTRY, TOOL_SCHEMAS
from agent.session import get_messages_for_prompt, add_turn
from agent.safety import validate_tool_args, is_write_action

# Initialize database
init_db()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_assistant")

app = FastAPI(title="Personal Voice Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

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


class ChatResponse(BaseModel):
    spoken_reply: str
    tool_calls_executed: List[Dict[str, Any]] = []
    requires_confirmation: bool = False
    confirmation_question: Optional[str] = None
    session_id: str
    latency_ms: float


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "alloy"
    speed: Optional[float] = 1.0


def _clean_spoken_text(text: str) -> str:
    """Strip markdown formatting, symbols, and bullets for natural voice synthesis."""
    if not text:
        return ""
    # Strip markdown headers
    t = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Strip bold / italics markdown
    t = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", t)
    # Strip list item bullets
    t = re.sub(r"^\s*[-*•]\s*", "", t, flags=re.MULTILINE)
    # Strip code blocks
    t = re.sub(r"`{1,3}[^`]*`{1,3}", "", t)
    # Collapse newlines into spaces
    t = re.sub(r"\n+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


ACTIVE_TOOL_NAMES = {"web_search", "calculator", "run_python_code", "get_current_time", "open_app", "send_whatsapp_message"}
ACTIVE_TOOL_SCHEMAS = [s for s in TOOL_SCHEMAS if s.get("function", {}).get("name") in ACTIVE_TOOL_NAMES]


async def process_user_turn(user_text: str, session_id: str) -> Dict[str, Any]:
    """Execute voice turn equipped with active tools:
    - web_search (live cricket scores, latest breaking news, real-time facts)
    - calculator (math expressions, arithmetic, percentages, powers, square roots)
    - run_python_code (execute basic Python code snippets, test algorithms, logic)
    - get_current_time (time and date)
    - LLM internal reasoning & general knowledge
    """
    start_time = time.perf_counter()
    clean_text = user_text.strip()
    session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"

    spoken = ""
    executed_tools: List[Dict[str, Any]] = []

    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-"):
        try:
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            history = get_messages_for_prompt(session_id)
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages.extend(history)
            messages.append({"role": "user", "content": clean_text})

            # Fast multi-step tool reasoning loop (capped at 3 steps)
            for _step in range(3):
                response = await client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    tools=ACTIVE_TOOL_SCHEMAS,
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=300,
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

                messages.extend(step_tool_results)

        except Exception as e:
            logger.error(f"OpenAI turn error: {e}")

    # Fallback if no LLM reply
    if not spoken:
        if executed_tools:
            last_tool = executed_tools[-1].get("result", {})
            if isinstance(last_tool, dict) and last_tool.get("spoken"):
                spoken = last_tool["spoken"]
        else:
            lower = clean_text.lower()
            if any(k in lower for k in ["news", "cricket", "score", "vs", "match", "search", "who is", "what is"]):
                res = TOOLS_REGISTRY["web_search"](query=clean_text)
                executed_tools.append({"tool": "web_search", "args": {"query": clean_text}, "result": res})
                spoken = res.get("spoken", "Found search information.")
            elif any(k in lower for k in ["calculate", "math", "+", "-", "*", "/", "%", "sqrt", "**", "//"]):
                expr = clean_text.replace("calculate", "").replace("what is", "").strip()
                res = TOOLS_REGISTRY["calculator"](expression=expr or clean_text)
                executed_tools.append({"tool": "calculator", "args": {"expression": expr}, "result": res})
                spoken = res.get("spoken", "Calculated the expression.")
            elif "whatsapp" in lower and any(w in lower for w in ["message", "text", "send", "chat", "to", "him", "her"]):
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
            elif any(k in lower for k in ["open", "launch", "play on youtube"]) or any(k in lower for k in ["youtube", "whatsapp", "linkedin", "gmail", "mail", "spotify"]):
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
                if target == "youtube" and any(w in lower for w in ["play", "search", "watch"]):
                    query_val = re.sub(r"^(open|play|search for|search|watch)\s+", "", clean_text, flags=re.IGNORECASE)
                    query_val = re.sub(r"\s+on youtube$", "", query_val, flags=re.IGNORECASE).strip()
                    if query_val.lower() == "youtube":
                        query_val = None
                res = TOOLS_REGISTRY["open_app"](name=target, query=query_val, browser=browser_pref)
                executed_tools.append({"tool": "open_app", "args": {"name": target, "query": query_val, "browser": browser_pref}, "result": res})
                spoken = res.get("spoken", f"Opening {target}.")
            elif "time" in lower:
                res = TOOLS_REGISTRY["get_current_time"]()
                executed_tools.append({"tool": "get_current_time", "args": {}, "result": res})
                spoken = res.get("spoken", "Checked the current time.")
            else:
                spoken = f"I am your personal voice assistant. You said: '{clean_text}'. How can I help you today?"

    add_turn(session_id, clean_text, spoken)
    latency = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "spoken_reply": spoken,
        "tool_calls_executed": executed_tools,
        "requires_confirmation": False,
        "session_id": session_id,
        "latency_ms": latency,
    }


# --- Web Frontend Static Files & Routes ---
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
INDEX_PATH = os.path.join(WEB_DIR, "index.html")

if os.path.exists(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index_page():
    """Serve Voice Assistant Web Interface."""
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return {"message": "Nexus Voice Assistant running on localhost:8000."}


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
        "llm_ready": bool(OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-")),
        "service": "Nexus Personal Voice Assistant",
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
    if not user:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}


@app.post("/api/auth/logout")
def auth_logout(authorization: Optional[str] = Header(None)):
    """Log out and invalidate current session token."""
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        db_delete_session_token(token)
    return {"success": True}


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

    result = await process_user_turn(user_text=req.message, session_id=sess_id)

    # Save to user's permanent history
    db_save_chat_turn(
        user_id=user_id,
        session_id=sess_id,
        user_message=req.message,
        spoken_reply=result["spoken_reply"],
        tool_calls=result.get("tool_calls_executed", []),
        latency_ms=result.get("latency_ms", 0.0),
    )

    return ChatResponse(**result)


@app.post("/api/stt")
async def stt_endpoint(file: UploadFile = File(...)):
    """Transcribe speech audio file using Whisper."""
    content = await file.read()
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-"):
        try:
            import io
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            audio_io = io.BytesIO(content)
            audio_io.name = file.filename or "speech.webm"
            tr = await client.audio.transcriptions.create(model="whisper-1", file=audio_io)
            return {"success": True, "text": tr.text.strip()}
        except Exception as e:
            logger.error(f"Whisper error: {e}")

    return {"success": True, "text": "Speech received and processed."}


@app.post("/api/tts")
async def tts_endpoint(req: TTSRequest):
    """Synthesize text to speech MP3 audio."""
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-"):
        try:
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
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

    # Fallback minimalist valid audio header
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

