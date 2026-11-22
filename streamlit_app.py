"""AI Assistant — Streamlit Web & Cloud Application.
ChatGPT-style Minimalist UI with Real-Time Web Search, Voice Synthesis & App Launching.
"""

import asyncio
import io
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
import streamlit as st
from dotenv import load_dotenv

# Ensure root directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Load environment variables (.env locally, st.secrets on Streamlit Cloud)
load_dotenv(override=True)
try:
    for key, val in st.secrets.items():
        if isinstance(val, str) and key not in os.environ:
            os.environ[key] = val
except Exception:
    pass

# Default to Local Ollama model
if "model_engine_choice" not in st.session_state:
    st.session_state.model_engine_choice = "Local Ollama (Offline / Free)"
    os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
    os.environ["OPENAI_MODEL"] = "qwen2.5:1.5b"
    os.environ.setdefault("OPENAI_API_KEY", "ollama")

from openai import OpenAI
from agent.main import process_user_turn, OPENAI_MODEL
from agent.tools import TOOLS_REGISTRY
from agent.voice import clean_spoken_text
from db.models import (
    get_db_connection,
    db_get_session_turns,
    db_save_chat_turn,
    db_clear_chat_history,
    db_get_user_email_profile,
    db_save_user_email_profile,
    db_get_user_oauth,
    db_delete_user_oauth,
)

logger = logging.getLogger("ai_assistant.streamlit")

# --------------------------------------------------------------------------- #
# Streamlit Page Setup & Custom Styling (ChatGPT Aesthetic)
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="AI Assistant — Voice & Web Search AI",
    page_icon="AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    /* Global Base - ChatGPT Dark Palette */
    .stApp {
        background-color: #212121 !important;
        color: #ececec !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #171717 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    /* ChatGPT Centered Welcome Screen */
    .chatgpt-center-hero {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        margin-top: 60px;
        margin-bottom: 30px;
    }
    .chatgpt-title {
        font-size: 34px;
        font-weight: 600;
        color: #ececec;
        letter-spacing: -0.6px;
        margin-bottom: 12px;
    }
    .chatgpt-sub {
        font-size: 15px;
        color: #9ca3af;
        margin-bottom: 36px;
    }

    /* ChatGPT Suggestion Cards Grid */
    .chatgpt-prompt-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 12px;
        max-width: 760px;
        width: 100%;
        margin: 0 auto 30px auto;
    }
    .chatgpt-prompt-box {
        background: #2f2f2f;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 16px 20px;
        text-align: left;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .chatgpt-prompt-box:hover {
        background: #383838;
        border-color: rgba(255, 255, 255, 0.2);
    }
    .chatgpt-prompt-title {
        font-size: 14px;
        font-weight: 600;
        color: #ececec;
        margin-bottom: 4px;
    }
    .chatgpt-prompt-desc {
        font-size: 12px;
        color: #9ca3af;
    }

    /* Line-by-Line Chat Bubbles */
    .chatgpt-bubble-user {
        background-color: #2f2f2f;
        color: #f3f4f6;
        border-radius: 24px;
        padding: 14px 22px;
        max-width: 76%;
        margin-left: auto;
        margin-bottom: 24px;
        font-size: 15px;
        line-height: 1.6;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        word-wrap: break-word;
    }
    .chatgpt-bubble-assistant {
        background-color: transparent;
        color: #ececec;
        padding: 4px 12px;
        max-width: 90%;
        margin-right: auto;
        margin-bottom: 28px;
        font-size: 15px;
        line-height: 1.7;
    }
    .chatgpt-avatar-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
    }
    .chatgpt-avatar-icon {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        background: linear-gradient(135deg, #10b981, #059669);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 15px;
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
    }
    .chatgpt-author-name {
        font-size: 13px;
        font-weight: 700;
        color: #e5e7eb;
    }
    .chatgpt-latency-pill {
        font-size: 11px;
        font-weight: 600;
        color: #9ca3af;
        background: rgba(255, 255, 255, 0.06);
        padding: 2px 8px;
        border-radius: 12px;
    }

    /* Tool Action Cards */
    .chatgpt-tool-card {
        margin-top: 14px;
        padding: 12px 18px;
        background: #1e1e1e;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
    }
    .chatgpt-tool-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 7px 16px;
        background: #2563eb;
        color: #ffffff !important;
        font-weight: 600;
        font-size: 12px;
        border-radius: 10px;
        text-decoration: none !important;
        transition: all 0.2s ease;
    }
    .chatgpt-tool-btn:hover {
        background: #1d4ed8;
    }

    /* ChatGPT Pill Input Styling (Matching Image 2) */
    div[data-testid="stChatInput"] {
        background: transparent !important;
        padding-bottom: 20px;
    }
    div[data-testid="stChatInput"] > div {
        background-color: #2f2f2f !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        border-radius: 32px !important;
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35) !important;
        padding: 8px 18px !important;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stChatInput"] > div:focus-within {
        border-color: rgba(255, 255, 255, 0.35) !important;
    }
    div[data-testid="stChatInput"] textarea {
        color: #ececec !important;
        font-size: 15px !important;
        font-family: inherit !important;
    }
    div[data-testid="stChatInput"] button {
        background-color: #ffffff !important;
        border-radius: 50% !important;
        color: #000000 !important;
        width: 34px !important;
        height: 34px !important;
        border: none !important;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    div[data-testid="stChatInput"] button:hover {
        background-color: #e5e7eb !important;
    }

    /* Voice Search Capsule Styling (ChatGPT Aesthetic) */
    div[data-testid="stAudioInput"] {
        max-width: 768px !important;
        margin: 0 auto 12px auto !important;
        background-color: #2f2f2f !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 28px !important;
        padding: 4px 16px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important;
    }
    div[data-testid="stAudioInput"] > div {
        background-color: transparent !important;
    }
    div[data-testid="stAudioInput"] button {
        background-color: #ef4444 !important;
        color: #ffffff !important;
        border-radius: 50% !important;
        box-shadow: 0 0 10px rgba(239, 68, 68, 0.4) !important;
        border: none !important;
    }
    div[data-testid="stAudioInput"] * {
        color: #ececec !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Session State & Query Param Initialization
# --------------------------------------------------------------------------- #
if "gmail_connected" in st.query_params:
    st.query_params.clear()
    st.rerun()

if "session_id" not in st.session_state:
    st.session_state.session_id = f"sess-{uuid.uuid4().hex[:8]}"

if "messages" not in st.session_state:
    st.session_state.messages = []
    existing_turns = db_get_session_turns(user_id="guest", session_id=st.session_state.session_id)
    for t in existing_turns:
        st.session_state.messages.append({
            "role": "user",
            "content": t["user_message"],
            "timestamp": t.get("created_at", "Past"),
            "input_mode": "voice",
        })
        st.session_state.messages.append({
            "role": "assistant",
            "content": t["spoken_reply"],
            "tool_calls": t.get("tool_calls", []),
            "latency_ms": t.get("latency_ms", 0.0),
            "timestamp": t.get("created_at", "Past"),
        })

if "auto_speech" not in st.session_state:
    st.session_state.auto_speech = True

if "speech_speed" not in st.session_state:
    st.session_state.speech_speed = 1.0

if "voice_name" not in st.session_state:
    st.session_state.voice_name = "alloy"

if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = None


# --------------------------------------------------------------------------- #
# Helper Functions: Whisper STT & OpenAI TTS
# --------------------------------------------------------------------------- #
def transcribe_uploaded_audio(audio_data: bytes) -> str:
    """Send voice audio recording to OpenAI Whisper API or local faster-whisper."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key and openai_key.startswith("sk-"):
        try:
            # Explicitly use official OpenAI API endpoint for Whisper
            client = OpenAI(api_key=openai_key, base_url="https://api.openai.com/v1")
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "recording.wav"
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
            return transcription.text.strip()
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")

    # 100% Offline Local faster-whisper fallback
    try:
        from agent.local_voice import transcribe_audio_local
        return transcribe_audio_local(audio_data)
    except Exception as e:
        logger.error(f"Local transcription error: {e}")
        return ""


def synthesize_speech(text: str, voice: str = "alloy", speed: float = 1.0) -> bytes:
    """Convert spoken text to MP3 audio via OpenAI TTS or local neural Edge-TTS."""
    clean_text = clean_spoken_text(text)
    if not clean_text:
        return b""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key and openai_key.startswith("sk-"):
        try:
            # Explicitly use official OpenAI API endpoint for TTS
            client = OpenAI(api_key=openai_key, base_url="https://api.openai.com/v1")
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=clean_text[:4096],
                speed=speed,
                response_format="mp3",
            )
            return response.content
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")

    # 100% Free Local Neural Edge-TTS fallback
    try:
        from agent.local_voice import synthesize_speech_local
        return synthesize_speech_local(clean_text)
    except Exception as e:
        logger.error(f"Local TTS error: {e}")
        return b""


def execute_turn(user_prompt: str, input_mode: str = "voice"):
    """Run full conversational turn with Web Search and tool dispatch."""
    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        return

    now_str = datetime.now(timezone.utc).strftime("%I:%M %p")
    st.session_state.messages.append({
        "role": "user",
        "content": clean_prompt,
        "timestamp": now_str,
        "input_mode": input_mode,
    })

    # Render user message immediately so it is never hidden while thinking
    prefix = "[Voice] " if input_mode == "voice" else ""
    st.markdown(
        f"""
        <div class="chatgpt-bubble-user">
            {prefix}{clean_prompt}
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.spinner("Searching & thinking..."):
        try:
            result = asyncio.run(process_user_turn(
                user_text=clean_prompt,
                session_id=st.session_state.session_id,
                user_id="keshav",
            ))
        except Exception as err:
            result = {
                "spoken_reply": f"An error occurred: {err}",
                "tool_calls_executed": [],
                "requires_confirmation": False,
                "latency_ms": 0.0,
            }

    spoken_reply = result.get("spoken_reply", "")
    tool_calls = result.get("tool_calls_executed", [])
    requires_confirm = result.get("requires_confirmation", False)
    confirm_q = result.get("confirmation_question")
    latency_ms = result.get("latency_ms", 0.0)

    audio_bytes = None
    if st.session_state.auto_speech and spoken_reply:
        audio_bytes = synthesize_speech(
            spoken_reply,
            voice=st.session_state.voice_name,
            speed=st.session_state.speech_speed,
        )

    msg_entry = {
        "role": "assistant",
        "content": spoken_reply,
        "tool_calls": tool_calls,
        "audio_bytes": audio_bytes,
        "requires_confirmation": requires_confirm,
        "confirmation_question": confirm_q,
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc).strftime("%I:%M %p"),
    }
    st.session_state.messages.append(msg_entry)

    try:
        db_save_chat_turn(
            user_id="keshav",
            session_id=st.session_state.session_id,
            user_message=clean_prompt,
            spoken_reply=spoken_reply,
            tool_calls=tool_calls,
            latency_ms=latency_ms,
        )
    except Exception as db_err:
        logger.warning(f"Failed to persist chat turn: {db_err}")


# --------------------------------------------------------------------------- #
# CHATGPT SIDEBAR: Controls & Engine Options
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 24px; padding: 4px;">
            <div style="font-size: 20px; background: #2f2f2f; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255,255,255,0.1);">AI</div>
            <div>
                <h3 style="margin: 0; font-size: 16px; font-weight: 700; color: #ececec;">AI Assistant</h3>
                <p style="margin: 0; font-size: 11px; color: #9ca3af;">Web Search & Real-Time Voice</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Voice Settings")
    st.session_state.auto_speech = st.toggle("Auto-Play Voice", value=st.session_state.auto_speech)
    st.session_state.voice_name = st.selectbox(
        "Persona:",
        options=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        index=["alloy", "echo", "fable", "onyx", "nova", "shimmer"].index(st.session_state.voice_name),
    )
    st.session_state.speech_speed = st.select_slider(
        "Speed:",
        options=[0.85, 1.0, 1.15, 1.25, 1.5],
        value=st.session_state.speech_speed,
        format_func=lambda s: f"{s}x",
    )

    st.markdown("---")
    st.markdown("#### AI Model Engine")
    model_choice = st.radio(
        "Engine:",
        options=["Local Ollama (Offline / Free)", "OpenAI GPT-4o (Cloud API)"],
        index=0 if "Local" in str(st.session_state.get("model_engine_choice", "Local")) else 1,
        key="model_engine_choice",
    )
    if "Local" in model_choice:
        local_model = st.selectbox(
            "Ollama Model:",
            options=["qwen2.5:1.5b"],
            index=0,
        )
        local_url = st.text_input("Endpoint:", value="http://localhost:11434/v1")
        os.environ["OPENAI_BASE_URL"] = local_url
        os.environ["OPENAI_MODEL"] = local_model
        os.environ["OPENAI_API_KEY"] = "ollama"
        st.caption(f"Connected to local `{local_model}` via `{local_url}`")
    else:
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ["OPENAI_MODEL"] = "gpt-4o"
        st.caption("Using Cloud OpenAI GPT-4o with Web Search & Multilingual Support")

    st.markdown("---")
    st.markdown("#### Google Account (1-Click Login)")

    oauth_rec = db_get_user_oauth("keshav") or db_get_user_oauth("krish") or db_get_user_oauth("guest")
    google_connected_email = oauth_rec.get("email") if oauth_rec and (oauth_rec.get("access_token") or oauth_rec.get("refresh_token")) else None

    def get_google_login_url():
        import urllib.parse
        import base64
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback").strip()
        if not client_id:
            return ""
        scopes = [
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/userinfo.email",
        ]
        state_payload = json.dumps({"user_id": "keshav", "source": "streamlit"})
        state_b64 = base64.urlsafe_b64encode(state_payload.encode("utf-8")).decode("utf-8")
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "state": state_b64,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    if google_connected_email:
        st.markdown(
            f"""
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 14px; padding: 14px; margin-bottom: 12px;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                    <span style="font-size: 13px; font-weight: 700; color: #10b981;">Logged In With Google</span>
                    <span style="font-size: 10px; background: rgba(16, 185, 129, 0.25); color: #10b981; padding: 2px 8px; border-radius: 10px; font-weight: 700;">Gmail OAuth</span>
                </div>
                <div style="font-size: 13px; color: #ececec; font-weight: 600; word-break: break-all;">{google_connected_email}</div>
                <div style="font-size: 11px; color: #9ca3af; margin-top: 6px;">No App Password needed! All emails will be sent directly from this address.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Logout from Google", use_container_width=True):
            db_delete_user_oauth("keshav")
            db_delete_user_oauth("krish")
            db_delete_user_oauth("guest")
            st.success("Logged out successfully!")
            st.rerun()
    else:
        st.markdown(
            """
            <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; padding: 12px 14px; margin-bottom: 12px;">
                <div style="font-size: 13px; font-weight: 600; color: #ececec; margin-bottom: 4px;">Sign in with your Google account</div>
                <div style="font-size: 11px; color: #9ca3af;">No App Passwords required. 1-click login allows AI Assistant to send emails from your own Gmail ID.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        login_url = get_google_login_url()
        if login_url:
            st.link_button("Login with Google", login_url, use_container_width=True)
        else:
            st.warning("Google OAuth credentials missing in .env")

    with st.expander("Alternative: Manual App Password (Optional)"):
        existing_profile = db_get_user_email_profile("keshav") or db_get_user_email_profile("krish") or {}
        default_name = existing_profile.get("sender_name") or "Keshav"
        default_email = existing_profile.get("sender_email") or os.environ.get("SENDER_EMAIL", "")
        default_has_pw = bool(existing_profile.get("sender_password") or os.environ.get("SENDER_APP_PASSWORD"))

        prof_name = st.text_input("Name:", value=default_name, key="profile_name_input")
        prof_email = st.text_input("Sender Email ID:", value=default_email, key="profile_email_input", placeholder="keshav@gmail.com")
        prof_password = st.text_input(
            "Gmail App Password (16-char):",
            type="password",
            placeholder="•••• •••• •••• ••••" if default_has_pw else "Enter 16-character password",
            key="profile_pw_input",
        )
        if st.button("Save App Password", use_container_width=True):
            pw_to_save = prof_password.strip() if prof_password.strip() else (existing_profile.get("sender_password") or os.environ.get("SENDER_APP_PASSWORD"))
            db_save_user_email_profile(
                user_id="keshav",
                sender_name=prof_name.strip() or "Keshav",
                sender_email=prof_email.strip(),
                sender_password=pw_to_save,
            )
            if prof_email.strip():
                os.environ["SENDER_EMAIL"] = prof_email.strip()
            if pw_to_save:
                os.environ["SENDER_APP_PASSWORD"] = pw_to_save
            st.success(f"Saved sender profile: {prof_name} <{prof_email}>")
            st.rerun()

    st.markdown("---")
    col_new, col_del = st.columns(2)
    with col_new:
        if st.button("New Chat", use_container_width=True):
            st.session_state.session_id = f"sess-{uuid.uuid4().hex[:8]}"
            st.session_state.messages = []
            st.rerun()
    with col_del:
        if st.button("Clear", use_container_width=True):
            db_clear_chat_history(user_id="guest", session_id=st.session_state.session_id)
            st.session_state.messages = []
            st.rerun()


# =========================================================================== #
# MAIN CHAT CANVAS (Pure ChatGPT + Web Search)
# =========================================================================== #

# ChatGPT Centered Welcome Screen (When no messages yet, exactly as Image 2)
if not st.session_state.messages:
    st.markdown(
        """
        <div class="chatgpt-center-hero">
            <h1 class="chatgpt-title">What’s on your mind today?</h1>
            <p class="chatgpt-sub">Ask any question, search the web for latest news & live info, solve math, or launch web apps.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 4 Quick Web Search & Assistant Suggestions (2x2 Grid like ChatGPT)
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        if st.button("Search latest world news\n\nFind top breaking headlines and tech stories today", key="sug_1", use_container_width=True):
            execute_turn("Search the web for the latest world news and top headlines today", input_mode="text")
            st.rerun()
        if st.button("Medicine Information Guide\n\nAsk about uses, dosage, and side effects of Dolo 650 or Paracetamol", key="sug_2", use_container_width=True):
            execute_turn("What is Dolo 650 used for and what are its dosage and side effects?", input_mode="text")
            st.rerun()
    with p_col2:
        if st.button("Live cricket scores & updates\n\nCheck current international match scorecards", key="sug_3", use_container_width=True):
            execute_turn("What is the latest cricket match score and status?", input_mode="text")
            st.rerun()
        if st.button("Math & Finance Calculation\n\nCalculate 18% GST on $1,250 and split 3 ways", key="sug_4", use_container_width=True):
            execute_turn("What is 1250 * 1.18 / 3?", input_mode="text")
            st.rerun()

# Active Conversation View (Clean Line-by-Line Bubbles)
for idx, msg in enumerate(st.session_state.messages):
    ts = msg.get("timestamp", "")
    role = msg.get("role")
    content = msg.get("content", "")

    if role == "user":
        st.markdown(
            f"""
            <div class="chatgpt-bubble-user">
                {content}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        lat = f"{msg.get('latency_ms', 0):.0f}ms" if msg.get("latency_ms") else ""
        st.markdown(
            f"""
            <div class="chatgpt-bubble-assistant">
                <div class="chatgpt-avatar-header">
                    <div class="chatgpt-avatar-icon">AI</div>
                    <span class="chatgpt-author-name">Assistant</span>
                    <span class="chatgpt-latency-pill">{lat}</span>
                    <span class="chatgpt-latency-pill">{ts}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Render response with markdown and math
        st.markdown(content)

        if msg.get("audio_bytes"):
            st.audio(msg["audio_bytes"], format="audio/mp3", autoplay=(idx == len(st.session_state.messages) - 1))

        tools = msg.get("tool_calls", [])
        if tools:
            for tc in tools:
                t_name = tc.get("tool", "")
                t_args = tc.get("args", {})
                t_res = tc.get("result", {})

                if t_name == "web_search" and t_res.get("success"):
                    st.markdown(
                        f"""
                        <div class="chatgpt-tool-card">
                            <div><strong>Web Search:</strong> <code>{t_args.get('query')}</code></div>
                            <span style="font-size: 11px; color: #9ca3af;">{len(t_res.get('results', []))} web sources referenced</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                elif t_name == "open_app" and t_res.get("url"):
                    t_label = t_res.get("target", "Application")
                    t_url = t_res.get("url")
                    st.markdown(
                        f"""
                        <div class="chatgpt-tool-card">
                            <div><strong>Opening {t_label}:</strong> <code>{t_args.get('query') or t_label}</code></div>
                            <a href="{t_url}" target="_blank" class="chatgpt-tool-btn">Open {t_label}</a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if idx == len(st.session_state.messages) - 1:
                        import streamlit.components.v1 as components
                        components.html(
                            f"""
                            <script>
                                window.open("{t_url}", "_blank");
                            </script>
                            """,
                            height=0,
                            width=0,
                        )

                elif t_name == "calculator" and t_res.get("success"):
                    st.markdown(
                        f"""
                        <div class="chatgpt-tool-card">
                            <div><strong>Math Calculation:</strong> <code>{t_args.get('expression')}</code></div>
                            <span style="font-size: 15px; font-weight: 700; color: #38bdf8;">= {t_res.get('formatted', t_res.get('result'))}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                elif t_name == "medical_search" and t_res.get("success"):
                    med_item = t_res.get("medicine", t_args.get("medicine_name", "Medicine"))
                    gen_name = t_res.get("generic_name", "")
                    drug_cl = t_res.get("drug_class", "")
                    uses_txt = t_res.get("uses", "")
                    dosage_txt = t_res.get("dosage_guidelines", "")
                    side_eff = t_res.get("side_effects", "")
                    precaut = t_res.get("precautions", "")
                    st.markdown(
                        f"""
                        <div class="chatgpt-tool-card" style="border-left: 3px solid #10b981; flex-direction: column; align-items: flex-start; gap: 8px;">
                            <div style="display: flex; justify-content: space-between; width: 100%; align-items: center;">
                                <div><strong>Medicine Information:</strong> <code>{med_item}</code> <span style="font-size: 11px; color: #10b981; margin-left: 8px;">{drug_cl}</span></div>
                                <span style="font-size: 11px; color: #9ca3af;">Clinical Reference</span>
                            </div>
                            <div style="font-size: 12px; color: #d1d5db; line-height: 1.5;">
                                <div><strong>Generic:</strong> {gen_name}</div>
                                <div><strong>Uses:</strong> {uses_txt}</div>
                                <div><strong>Dosage:</strong> {dosage_txt}</div>
                                <div><strong>Side Effects:</strong> {side_eff}</div>
                                <div><strong>Precautions:</strong> {precaut}</div>
                            </div>
                            <div style="font-size: 10px; color: #9ca3af; margin-top: 4px; font-style: italic;">
                                {t_res.get('disclaimer', '')}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

# --------------------------------------------------------------------------- #
# LiveKit WebRTC Real-Time Voice Studio (Exclusive Voice Mode)
# --------------------------------------------------------------------------- #
def get_livekit_connection():
    url = os.environ.get("LIVEKIT_URL", "").strip()
    key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    if not (url and key and secret):
        return None
    try:
        from livekit import api
        user_name = "Keshav"
        user_id = "keshav"
        participant_id = f"user-keshav-{uuid.uuid4().hex[:6]}"
        room_name = "nexus-room"
        meta = json.dumps({"user_id": user_id, "name": user_name})
        token = (
            api.AccessToken(key, secret)
            .with_identity(participant_id)
            .with_name(user_name)
            .with_metadata(meta)
            .with_grants(api.VideoGrants(room_join=True, room=room_name))
            .to_jwt()
        )
        return {
            "url": url,
            "token": token,
            "room": room_name,
            "identity": participant_id,
            "name": user_name,
        }
    except Exception as e:
        logger.error(f"LiveKit token minting error: {e}")
        return None

livekit_data = get_livekit_connection()
if livekit_data:
    lk_url = livekit_data["url"]
    lk_token = livekit_data["token"]
    import streamlit.components.v1 as components
    components.html(
        f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <script src="https://cdn.jsdelivr.net/npm/livekit-client@2.6.0/dist/livekit-client.umd.min.js"></script>
          <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
            body {{ background: transparent; color: #ececec; padding: 2px; }}
            .lk-box {{
              max-width: 768px;
              margin: 0 auto;
              background: #262626;
              border: 1px solid rgba(255, 255, 255, 0.15);
              border-radius: 24px;
              padding: 10px 18px;
              display: flex;
              align-items: center;
              justify-content: space-between;
              box-shadow: 0 4px 18px rgba(0, 0, 0, 0.4);
              gap: 12px;
            }}
            .lk-left {{
              display: flex;
              align-items: center;
              gap: 12px;
            }}
            .lk-status-indicator {{
              width: 14px;
              height: 14px;
              border-radius: 50%;
              background: #10b981;
              box-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
              transition: all 0.3s ease;
            }}
            .lk-status-indicator.connected {{
              background: #ef4444;
              box-shadow: 0 0 14px rgba(239, 68, 68, 0.8);
              animation: lk-pulse 1.4s infinite;
            }}
            .lk-wave {{
              display: none;
              align-items: center;
              gap: 3px;
              height: 16px;
            }}
            .lk-wave.active {{
              display: flex;
            }}
            .lk-wave .bar {{
              width: 3px;
              height: 100%;
              background: #10b981;
              border-radius: 2px;
              animation: wave-bar 0.8s ease-in-out infinite alternate;
            }}
            .lk-wave .bar:nth-child(2) {{ animation-delay: 0.15s; }}
            .lk-wave .bar:nth-child(3) {{ animation-delay: 0.30s; }}
            .lk-wave .bar:nth-child(4) {{ animation-delay: 0.45s; }}
            @keyframes wave-bar {{
              0% {{ height: 4px; }}
              100% {{ height: 16px; }}
            }}
            @keyframes lk-pulse {{
              0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }}
              70% {{ transform: scale(1.15); box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }}
              100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }}
            }}
            .lk-title {{
              font-size: 13px;
              font-weight: 700;
              color: #f3f4f6;
            }}
            .lk-sub {{
              font-size: 11px;
              color: #9ca3af;
            }}
            .lk-right {{
              display: flex;
              align-items: center;
              gap: 8px;
            }}
            .lk-btn {{
              display: inline-flex;
              align-items: center;
              gap: 6px;
              background: #10b981;
              color: #ffffff;
              border: none;
              border-radius: 20px;
              padding: 8px 18px;
              font-size: 13px;
              font-weight: 600;
              cursor: pointer;
              transition: all 0.2s ease;
            }}
            .lk-btn:hover {{
              background: #059669;
            }}
            .lk-btn.connected {{
              background: #ef4444;
            }}
            .lk-btn.connected:hover {{
              background: #dc2626;
            }}
            .lk-hub-btn {{
              display: inline-flex;
              align-items: center;
              background: rgba(255, 255, 255, 0.08);
              color: #9ca3af;
              border: 1px solid rgba(255, 255, 255, 0.12);
              border-radius: 20px;
              padding: 7px 14px;
              font-size: 12px;
              font-weight: 600;
              text-decoration: none;
              transition: all 0.2s ease;
            }}
            .lk-hub-btn:hover {{
              background: rgba(255, 255, 255, 0.15);
              color: #ffffff;
            }}
          </style>
        </head>
        <body>
          <div class="lk-box">
            <div class="lk-left">
              <div id="lk-dot" class="lk-status-indicator"></div>
              <div id="lk-wave" class="lk-wave">
                <span class="bar"></span>
                <span class="bar"></span>
                <span class="bar"></span>
                <span class="bar"></span>
              </div>
              <div>
                <div id="lk-title" class="lk-title">LiveKit Voice Agent (Sub-400ms)</div>
                <div id="lk-sub" class="lk-sub">Auto-VAD • Cloud WebRTC • Hands-Free (Speak naturally)</div>
              </div>
            </div>
            <div class="lk-right">
              <button id="lk-btn" class="lk-btn" onclick="toggleVoice()">
                <span id="lk-icon">MIC</span>
                <span id="lk-btn-text">Start LiveKit Voice</span>
              </button>
              <a href="http://localhost:8000/" target="_blank" class="lk-hub-btn" title="Open Full Standalone Voice Hub">
                Full Web Hub
              </a>
            </div>
          </div>

          <script>
            let currentRoom = null;
            let isConnecting = false;

            async function toggleVoice() {{
              if (currentRoom) {{
                await disconnectVoice();
              }} else {{
                await connectVoice();
              }}
            }}

            async function connectVoice() {{
              if (isConnecting) return;
              if (typeof LivekitClient === "undefined") {{
                alert("Loading LiveKit WebRTC client library... Please check your internet connection.");
                return;
              }}
              const btn = document.getElementById("lk-btn");
              const btnText = document.getElementById("lk-btn-text");
              const icon = document.getElementById("lk-icon");
              const dot = document.getElementById("lk-dot");
              const title = document.getElementById("lk-title");
              const sub = document.getElementById("lk-sub");

              try {{
                isConnecting = true;
                btnText.innerText = "Connecting...";
                title.innerText = "Connecting WebRTC to LiveKit Cloud...";
                
                currentRoom = new LivekitClient.Room({{
                  adaptiveStream: true,
                  dynacast: true,
                  audioCaptureDefaults: {{
                    autoGainControl: true,
                    echoCancellation: true,
                    noiseSuppression: true,
                  }},
                }});

                currentRoom.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {{
                  if (track.kind === LivekitClient.Track.Kind.Audio) {{
                    const existingAudio = document.getElementById(`audio-${{participant.identity}}`);
                    if (existingAudio) existingAudio.remove();
                    const audioEl = track.attach();
                    audioEl.id = `audio-${{participant.identity}}`;
                    audioEl.autoplay = true;
                    document.body.appendChild(audioEl);
                    audioEl.play().catch(e => {{
                      console.warn("Autoplay unlock:", e);
                      if (currentRoom.startAudio) currentRoom.startAudio();
                    }});
                  }}
                }});

                currentRoom.on(LivekitClient.RoomEvent.ActiveSpeakersChanged, (speakers) => {{
                  const wave = document.getElementById("lk-wave");
                  if (speakers.length > 0) {{
                    const isAssistant = speakers.some(s => !s.isLocal);
                    if (wave) wave.className = "lk-wave active";
                    if (isAssistant) {{
                      title.innerText = "AI Assistant is speaking...";
                      sub.innerText = "You can speak to interrupt anytime";
                    }} else {{
                      title.innerText = "Listening to Keshav...";
                      sub.innerText = "Silero VAD active (auto-stops when you pause)";
                    }}
                  }} else {{
                    if (wave) wave.className = "lk-wave";
                    title.innerText = "Connected to LiveKit (Listening...)";
                    sub.innerText = "Speak into microphone — auto-processes on silence";
                  }}
                }});

                currentRoom.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {{
                  try {{
                    const text = new TextDecoder().decode(payload);
                    const data = JSON.parse(text);
                    if (data.type === "OPEN_URL" && data.url) {{
                      window.open(data.url, "_blank");
                    }}
                  }} catch (e) {{
                    console.warn("LiveKit data packet parse error:", e);
                  }}
                }});

                currentRoom.on(LivekitClient.RoomEvent.TranscriptionReceived, (transcriptions, participant) => {{
                  if (transcriptions && transcriptions.length > 0) {{
                    const text = transcriptions.map(t => t.text).join(" ").trim();
                    if (!text) return;
                    const isAssistant = participant && !participant.isLocal;
                    if (isAssistant) {{
                      title.innerText = "AI: " + (text.length > 36 ? text.slice(0, 36) + "..." : text);
                      sub.innerText = text;
                    }} else {{
                      title.innerText = "You: " + (text.length > 36 ? text.slice(0, 36) + "..." : text);
                      sub.innerText = "Processing your voice command...";
                    }}
                  }}
                }});

                currentRoom.on(LivekitClient.RoomEvent.Disconnected, () => {{
                  resetVoiceUI();
                }});

                await currentRoom.connect("{lk_url}", "{lk_token}");
                if (currentRoom.canPlayAudio && !currentRoom.canPlayAudio()) {{
                  await currentRoom.startAudio();
                }}
                await currentRoom.localParticipant.setMicrophoneEnabled(true, {{
                  echoCancellation: true,
                  noiseSuppression: true,
                  autoGainControl: true,
                }});

                btn.className = "lk-btn connected";
                icon.innerText = "STOP";
                btnText.innerText = "Disconnect Voice";
                dot.className = "lk-status-indicator connected";
                title.innerText = "Connected to LiveKit (Listening...)";
                sub.innerText = "Speak into microphone — auto-processes on silence";
              }} catch (err) {{
                console.error("LiveKit connection error:", err);
                alert("Could not connect to LiveKit voice stream: " + err.message);
                resetVoiceUI();
              }} finally {{
                isConnecting = false;
              }}
            }}

            async function disconnectVoice() {{
              if (currentRoom) {{
                try {{ await currentRoom.disconnect(); }} catch (e) {{}}
                currentRoom = null;
              }}
              resetVoiceUI();
            }}

            function resetVoiceUI() {{
              currentRoom = null;
              isConnecting = false;
              const btn = document.getElementById("lk-btn");
              const btnText = document.getElementById("lk-btn-text");
              const icon = document.getElementById("lk-icon");
              const dot = document.getElementById("lk-dot");
              const wave = document.getElementById("lk-wave");
              const title = document.getElementById("lk-title");
              const sub = document.getElementById("lk-sub");

              if (btn) btn.className = "lk-btn";
              if (icon) icon.innerText = "MIC";
              if (btnText) btnText.innerText = "Start LiveKit Voice";
              if (dot) dot.className = "lk-status-indicator";
              if (wave) wave.className = "lk-wave";
              if (title) title.innerText = "LiveKit Voice Agent (Sub-400ms)";
              if (sub) sub.innerText = "Auto-VAD • Cloud WebRTC • Hands-Free (Speak naturally)";
            }}
          </script>
        </body>
        </html>
        """,
        height=72,
    )

# ChatGPT Capsule Text Input Bar
user_chat = st.chat_input("Ask anything or search the web...")

if user_chat:
    execute_turn(user_chat, input_mode="text")
    st.rerun()
