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

# Ensure Cloud GPT-4o is active by default
if "model_engine_choice" not in st.session_state or "Cloud" in str(st.session_state.get("model_engine_choice", "")):
    os.environ.pop("OPENAI_BASE_URL", None)
    os.environ["OPENAI_MODEL"] = "gpt-4o"

from openai import OpenAI
from agent.main import process_user_turn, OPENAI_MODEL
from agent.tools import TOOLS_REGISTRY
from agent.voice import clean_spoken_text
from db.models import (
    get_db_connection,
    db_get_session_turns,
    db_save_chat_turn,
    db_clear_chat_history,
)

logger = logging.getLogger("ai_assistant.streamlit")

# --------------------------------------------------------------------------- #
# Streamlit Page Setup & Custom Styling (ChatGPT Aesthetic)
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="AI Assistant — Voice & Web Search AI",
    page_icon="🤖",
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
# Session State Initialization
# --------------------------------------------------------------------------- #
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
    """Send voice audio recording to OpenAI Whisper API."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key or openai_key.startswith("your-"):
        return ""
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
        return ""


def synthesize_speech(text: str, voice: str = "alloy", speed: float = 1.0) -> bytes:
    """Convert spoken text to MP3 audio via OpenAI TTS."""
    clean_text = clean_spoken_text(text)
    if not clean_text:
        return b""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key or openai_key.startswith("your-"):
        return b""
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
    prefix = "🎙️ " if input_mode == "voice" else ""
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
                user_id="guest",
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
            user_id="guest",
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
            <div style="font-size: 20px; background: #2f2f2f; width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255,255,255,0.1);">🤖</div>
            <div>
                <h3 style="margin: 0; font-size: 16px; font-weight: 700; color: #ececec;">AI Assistant</h3>
                <p style="margin: 0; font-size: 11px; color: #9ca3af;">Web Search & Real-Time Voice</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### 🔊 Voice Settings")
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
    st.markdown("#### 🤖 Model Engine")
    model_choice = st.radio(
        "Engine:",
        options=["☁️ OpenAI GPT-4o (Recommended)", "🖥️ Local Ollama"],
        index=0,
        key="model_engine_choice",
    )
    if "Local" in model_choice:
        local_model = st.selectbox(
            "Ollama Model:",
            options=["rtu-senior:latest", "qwen2.5:1.5b"],
            index=0,
        )
        local_url = st.text_input("Endpoint:", value="http://localhost:11434/v1")
        os.environ["OPENAI_BASE_URL"] = local_url
        os.environ["OPENAI_MODEL"] = local_model
        st.caption(f"Connected to local `{local_model}`")
    else:
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ["OPENAI_MODEL"] = "gpt-4o"
        st.caption("Using Cloud OpenAI GPT-4o with Web Search & Multilingual Support")

    st.markdown("---")
    col_new, col_del = st.columns(2)
    with col_new:
        if st.button("➕ New Chat", use_container_width=True):
            st.session_state.session_id = f"sess-{uuid.uuid4().hex[:8]}"
            st.session_state.messages = []
            st.rerun()
    with col_del:
        if st.button("🗑️ Clear", use_container_width=True):
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
        if st.button("🔍 Search latest world news\n\nFind top breaking headlines and tech stories today", key="sug_1", use_container_width=True):
            execute_turn("Search the web for the latest world news and top headlines today", input_mode="text")
            st.rerun()
        if st.button("🏏 Live cricket scores & updates\n\nCheck current international match scorecards", key="sug_2", use_container_width=True):
            execute_turn("What is the latest cricket match score and status?", input_mode="text")
            st.rerun()
    with p_col2:
        if st.button("💡 How do quantum computers work?\n\nExplain qubits, superposition, and entanglement", key="sug_3", use_container_width=True):
            execute_turn("Explain how quantum computers work in simple terms", input_mode="text")
            st.rerun()
        if st.button("🧮 Math & Finance Calculation\n\nCalculate 18% GST on $1,250 and split 3 ways", key="sug_4", use_container_width=True):
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
                    <div class="chatgpt-avatar-icon">🤖</div>
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
                            <div>🔍 <strong>Web Search:</strong> <code>{t_args.get('query')}</code></div>
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
                            <div>🚀 <strong>Opening {t_label}:</strong> <code>{t_args.get('query') or t_label}</code></div>
                            <a href="{t_url}" target="_blank" class="chatgpt-tool-btn">Open {t_label} ↗</a>
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
                            <div>🧮 <strong>Math Calculation:</strong> <code>{t_args.get('expression')}</code></div>
                            <span style="font-size: 15px; font-weight: 700; color: #38bdf8;">= {t_res.get('formatted', t_res.get('result'))}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

# --------------------------------------------------------------------------- #
# Unified Voice Mode Capsule (Single Sleek ChatGPT Input)
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div style="max-width: 768px; margin: 20px auto 8px auto; display: flex; align-items: center; justify-content: space-between; padding: 0 6px;">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; background: #ef4444; border-radius: 50%; font-size: 12px; color: white;">🎙️</span>
            <span style="font-size: 13px; font-weight: 600; color: #ececec;">Voice Mode (Click red mic to speak):</span>
        </div>
        <span style="font-size: 11px; color: #9ca3af; background: rgba(255,255,255,0.06); padding: 3px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1);">Whisper AI Active</span>
    </div>
    """,
    unsafe_allow_html=True,
)

voice_audio = st.audio_input(
    "Voice Search",
    label_visibility="collapsed",
    key="chatgpt_voice_recorder",
)
if voice_audio is not None:
    audio_bytes = voice_audio.read()
    audio_hash = hash(audio_bytes)
    if st.session_state.last_processed_audio != audio_hash:
        st.session_state.last_processed_audio = audio_hash
        with st.spinner("Transcribing speech with Whisper AI..."):
            transcribed_text = transcribe_uploaded_audio(audio_bytes)
            if transcribed_text:
                execute_turn(transcribed_text, input_mode="voice")
                st.rerun()
            else:
                st.warning("Could not detect clear speech. Please speak again.")

# ChatGPT Capsule Text Input Bar
user_chat = st.chat_input("Ask anything or search the web...")

if user_chat:
    execute_turn(user_chat, input_mode="text")
    st.rerun()
