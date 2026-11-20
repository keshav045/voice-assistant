"""Nexus AI Senior Tutor & Exam Suite — Streamlit Web & Cloud Application.
Real-Time Line-by-Line Voice Conversation, Crash Course Planner, High-Yield Topics, Practice Quiz & Past Papers.
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

from openai import OpenAI
from agent.main import process_user_turn, OPENAI_MODEL
from agent.tools import TOOLS_REGISTRY
from agent.voice import clean_spoken_text
from db.models import (
    get_db_connection,
    db_list_chat_sessions,
    db_get_session_turns,
    db_save_chat_turn,
    db_clear_chat_history,
    db_add_task,
    db_list_tasks,
    db_add_note,
    db_list_notes,
    db_search_paper_chunks,
)
from evals.benchmark import (
    run_comprehensive_benchmark,
    generate_markdown_report,
)

logger = logging.getLogger("nexus.streamlit")

# --------------------------------------------------------------------------- #
# Streamlit Page Setup & Custom Styling
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Nexus Senior Tutor & Study Portal",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    /* Global Base */
    .stApp {
        background-color: #070b14;
        color: #f1f5f9;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Top Horizontal Navigation Tab Bar */
    .top-nav-container {
        display: flex;
        align-items: center;
        gap: 28px;
        border-bottom: 2px solid rgba(255, 255, 255, 0.08);
        padding-bottom: 12px;
        margin-bottom: 24px;
        overflow-x: auto;
    }
    .top-nav-item {
        font-size: 15px;
        font-weight: 600;
        color: #94a3b8;
        text-decoration: none;
        padding-bottom: 8px;
        position: relative;
        cursor: pointer;
        transition: all 0.2s ease;
        white-space: nowrap;
    }
    .top-nav-item:hover {
        color: #e2e8f0;
    }
    .top-nav-active {
        color: #38bdf8 !important;
        font-weight: 700;
        border-bottom: 3px solid #38bdf8;
    }

    /* Header Hero Banner */
    .nexus-hero {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 28px;
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(15, 23, 42, 0.95));
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 18px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
        backdrop-filter: blur(14px);
    }
    .nexus-title-wrap {
        display: flex;
        align-items: center;
        gap: 18px;
    }
    .nexus-orb-glow {
        width: 52px;
        height: 52px;
        border-radius: 16px;
        background: linear-gradient(135deg, #6366f1, #a855f7);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 26px;
        box-shadow: 0 0 24px rgba(99, 102, 241, 0.55);
    }
    .nexus-h1 {
        font-size: 24px;
        font-weight: 800;
        margin: 0;
        background: linear-gradient(90deg, #ffffff, #c7d2fe);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
    }
    .nexus-sub {
        font-size: 13px;
        color: #94a3b8;
        margin: 4px 0 0 0;
    }

    /* Waveform visualizer */
    .waveform-bar-box {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 18px;
        background: rgba(15, 23, 42, 0.9);
        border: 1px solid rgba(99, 102, 241, 0.35);
        border-radius: 30px;
    }
    .wave-line {
        width: 4px;
        height: 14px;
        background: #818cf8;
        border-radius: 4px;
        animation: waveAnim 1.2s infinite ease-in-out;
    }
    .wave-line:nth-child(2) { animation-delay: 0.2s; height: 22px; background: #a855f7; }
    .wave-line:nth-child(3) { animation-delay: 0.4s; height: 28px; background: #ec4899; }
    .wave-line:nth-child(4) { animation-delay: 0.6s; height: 18px; background: #6366f1; }
    .wave-line:nth-child(5) { animation-delay: 0.8s; height: 12px; background: #38bdf8; }
    @keyframes waveAnim {
        0%, 100% { transform: scaleY(0.4); }
        50% { transform: scaleY(1.3); }
    }
    .status-text {
        font-size: 11px;
        font-weight: 800;
        color: #38bdf8;
        margin-left: 8px;
        letter-spacing: 0.8px;
    }

    /* Line-by-Line Conversation Styling */
    .chat-line-user {
        background: rgba(30, 41, 59, 0.55);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-left: 4px solid #6366f1;
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 14px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }
    .chat-line-assistant {
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(16, 185, 129, 0.25);
        border-left: 4px solid #10b981;
        border-radius: 14px;
        padding: 18px 22px;
        margin-bottom: 18px;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
    }
    .speaker-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
        font-size: 12px;
        color: #94a3b8;
    }
    .speaker-tag {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .speaker-tag-user { color: #a5b4fc; }
    .speaker-tag-assistant { color: #6ee7b7; }
    .badge-pill {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-size: 11px;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.08);
        color: #cbd5e1;
    }
    .chat-text {
        font-size: 15px;
        line-height: 1.65;
        color: #f8fafc;
        margin: 0;
    }

    /* Cards & Blocks */
    .study-card {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 16px;
        padding: 20px 24px;
        margin-bottom: 18px;
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.3);
    }
    .tool-action-card {
        margin-top: 12px;
        padding: 12px 16px;
        background: rgba(2, 6, 23, 0.7);
        border: 1px solid rgba(99, 102, 241, 0.35);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
    }
    .tool-link-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px;
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        color: #ffffff !important;
        font-weight: 700;
        font-size: 12px;
        border-radius: 8px;
        text-decoration: none !important;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.4);
        transition: all 0.2s ease;
    }
    .tool-link-btn:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(79, 70, 229, 0.6);
    }

    /* Priority Badges */
    .badge-p0 {
        background: rgba(239, 68, 68, 0.15);
        color: #fca5a5;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 3px 8px;
        border-radius: 8px;
        font-size: 11px;
        font-weight: 700;
    }
    .badge-p1 {
        background: rgba(245, 158, 11, 0.15);
        color: #fcd34d;
        border: 1px solid rgba(245, 158, 11, 0.3);
        padding: 3px 8px;
        border-radius: 8px;
        font-size: 11px;
        font-weight: 700;
    }
    .badge-p2 {
        background: rgba(16, 185, 129, 0.15);
        color: #6ee7b7;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 3px 8px;
        border-radius: 8px;
        font-size: 11px;
        font-weight: 700;
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

if "active_tab" not in st.session_state:
    st.session_state.active_tab = "Senior Tutor Chat"

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

if "benchmark_results" not in st.session_state:
    st.session_state.benchmark_results = None

if "active_quiz" not in st.session_state:
    st.session_state.active_quiz = None


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
    """Run full Senior Tutor turn with tool dispatch and state update."""
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

    with st.spinner("Senior Tutor is reasoning & solving..."):
        try:
            result = asyncio.run(process_user_turn(
                user_text=clean_prompt,
                session_id=st.session_state.session_id,
                user_id="guest",
            ))
        except Exception as err:
            result = {
                "spoken_reply": f"An error occurred while answering your question: {err}",
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


def generate_tutor_response(prompt: str, system_role: str) -> str:
    """Generate high-quality academic tutor output using OpenAI GPT-4o or Local Ollama."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    current_model = os.environ.get("OPENAI_MODEL", OPENAI_MODEL)

    if (openai_key and not openai_key.startswith("your-")) or openai_base:
        try:
            client = OpenAI(api_key=openai_key or "local-model", base_url=openai_base)
            completion = client.chat.completions.create(
                model=current_model,
                messages=[
                    {"role": "system", "content": system_role},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Tutor generation failed: {e}")
    # Local fallback
    return f"Prepared tutor analysis for: {prompt}\n\nPlease review key concepts, formulas, and step-by-step notes in your textbooks."


# --------------------------------------------------------------------------- #
# STUDENT SIDEBAR: Clean, Focused Navigation Menu & Revision Sessions
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
            <div style="font-size: 26px; background: linear-gradient(135deg, #6366f1, #a855f7); width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(99,102,241,0.4);">🎓</div>
            <div>
                <h3 style="margin: 0; font-size: 17px; font-weight: 700; color: #f8fafc;">Nexus Study Portal</h3>
                <p style="margin: 0; font-size: 12px; color: #94a3b8;">Senior Tutor & Exam Suite</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    MODULE_NAMES = [
        "Senior Tutor Chat",
        "Crash Course Planner",
        "High-Yield Important Topics",
        "Practice Quiz & Evaluation",
        "Past Papers Archive",
    ]

    selected_sidebar_tab = st.radio(
        "STUDY MODULES",
        options=MODULE_NAMES,
        index=MODULE_NAMES.index(st.session_state.active_tab),
        key="sidebar_module_radio",
    )
    if selected_sidebar_tab != st.session_state.active_tab:
        st.session_state.active_tab = selected_sidebar_tab
        st.rerun()

    st.markdown("---")
    st.markdown("#### 🔊 Tutor Voice Controls")
    st.session_state.auto_speech = st.toggle("Auto-Play Spoken Voice", value=st.session_state.auto_speech)
    st.session_state.voice_name = st.selectbox(
        "Tutor Voice Persona",
        options=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        index=["alloy", "echo", "fable", "onyx", "nova", "shimmer"].index(st.session_state.voice_name),
    )
    st.session_state.speech_speed = st.select_slider(
        "Voice Speed:",
        options=[0.85, 1.0, 1.15, 1.25, 1.5],
        value=st.session_state.speech_speed,
        format_func=lambda s: f"{s}x {'(Fast)' if s > 1.0 else '(Normal)' if s == 1.0 else '(Slow)'}",
    )

    st.markdown("---")
    st.markdown("#### 🤖 AI Model Engine")
    model_mode = st.radio(
        "Mode:",
        options=["☁️ Cloud API (OpenAI GPT-4o)", "🖥️ Local Model (Ollama)"],
        index=0 if not os.environ.get("OPENAI_BASE_URL") else 1,
    )
    if "Local Model" in model_mode:
        local_model = st.selectbox(
            "Select Local Ollama Model:",
            options=["rtu-senior:latest", "qwen2.5:1.5b"],
            index=0,
        )
        local_url = st.text_input("Ollama Endpoint:", value="http://localhost:11434/v1")
        os.environ["OPENAI_BASE_URL"] = local_url
        os.environ["OPENAI_MODEL"] = local_model
        st.success(f"🟢 Using `{local_model}` on localhost:11434")
    else:
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ["OPENAI_MODEL"] = "gpt-4o"
        st.caption("Using Cloud OpenAI GPT-4o API")

    st.markdown("---")
    st.markdown("#### 📚 Revision Sessions")
    sessions = db_list_chat_sessions(user_id="guest", limit=15)
    session_options = [s["session_id"] for s in sessions]
    if st.session_state.session_id not in session_options:
        session_options.insert(0, st.session_state.session_id)

    def _switch_study_session():
        chosen_sess = st.session_state.get("study_session_selector")
        if chosen_sess and chosen_sess != st.session_state.session_id:
            st.session_state.session_id = chosen_sess
            st.session_state.messages = []
            existing = db_get_session_turns(user_id="guest", session_id=chosen_sess)
            for t in existing:
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

    curr_idx = session_options.index(st.session_state.session_id) if st.session_state.session_id in session_options else 0
    st.selectbox(
        "Study Session:",
        options=session_options,
        index=curr_idx,
        key="study_session_selector",
        on_change=_switch_study_session,
    )

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
            st.success("Cleared.")
            st.rerun()


# --------------------------------------------------------------------------- #
# Top Navigation Bar & Hero Banner (Matches Screenshot 1)
# --------------------------------------------------------------------------- #
# Render the 5 horizontal navigation tabs exactly matching the student portal design
top_nav_cols = st.columns(5)
for i, m_name in enumerate(MODULE_NAMES):
    with top_nav_cols[i]:
        is_active = (m_name == st.session_state.active_tab)
        btn_type = "primary" if is_active else "secondary"
        if st.button(m_name, key=f"nav_top_{i}", type=btn_type, use_container_width=True):
            st.session_state.active_tab = m_name
            st.rerun()

st.markdown(
    f"""
    <div class="nexus-hero">
        <div class="nexus-title-wrap">
            <div class="nexus-orb-glow">🎓</div>
            <div>
                <h1 class="nexus-h1">{st.session_state.active_tab}</h1>
                <p class="nexus-sub">Nexus AI Senior Academic Tutor • Real-Time Voice • Exam Strategy & Evaluation</p>
            </div>
        </div>
        <div class="waveform-bar-box">
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <span class="status-text">TUTOR ONLINE</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================================== #
# MODULE 1: Senior Tutor Chat (Line-by-Line Voice Conversation)
# =========================================================================== #
if st.session_state.active_tab == "Senior Tutor Chat":
    st.markdown("#### 🎤 Voice Recording Station")
    col_mic, col_tips = st.columns([2, 1])

    with col_mic:
        audio_input_data = st.audio_input("Ask Senior Tutor via Voice (click mic, speak question, click stop):")
        if audio_input_data is not None:
            audio_bytes = audio_input_data.read()
            audio_hash = hash(audio_bytes)
            if st.session_state.last_processed_audio != audio_hash:
                st.session_state.last_processed_audio = audio_hash
                with st.spinner("Transcribing speech with OpenAI Whisper..."):
                    transcribed_text = transcribe_uploaded_audio(audio_bytes)
                    if transcribed_text:
                        execute_turn(transcribed_text, input_mode="voice")
                        st.rerun()
                    else:
                        st.warning("Could not detect clear speech. Please speak again.")

    with col_tips:
        st.markdown("**⚡ Quick Academic Prompts:**")
        student_prompts = [
            "Explain QuickSort vs MergeSort step by step",
            "Solve: integral of x * e^(2x) dx",
            "What are the 3 laws of Thermodynamics with examples?",
            "What is 25 * 40 + 15% of 1000?",
        ]
        for p in student_prompts:
            if st.button(f"🗣️ {p}", key=f"chip_{p[:18]}", use_container_width=True):
                execute_turn(p, input_mode="text")
                st.rerun()

    st.markdown("---")
    st.markdown("### 💬 Line-by-Line Tutor Dialogue")

    if not st.session_state.messages:
        st.markdown(
            """
            <div style="text-align: center; padding: 48px 24px; color: #64748b; background: rgba(15, 23, 42, 0.45); border-radius: 18px; border: 1px dashed rgba(99, 102, 241, 0.35);">
                <div style="font-size: 46px; margin-bottom: 14px;">👋 🎓</div>
                <h3 style="color: #cbd5e1; font-weight: 700;">How can Senior Tutor help your exam prep today?</h3>
                <p style="font-size: 14px; max-width: 500px; margin: 0 auto; line-height: 1.6;">
                    Speak using the microphone above, click a quick academic prompt, or type any formula, derivation, or concept below!
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for idx, msg in enumerate(st.session_state.messages):
        ts = msg.get("timestamp", "")
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "user":
            mode_badge = "🎙️ VOICE INPUT" if msg.get("input_mode") == "voice" else "⌨️ TEXT INPUT"
            st.markdown(
                f"""
                <div class="chat-line-user">
                    <div class="speaker-meta">
                        <span class="speaker-tag speaker-tag-user">👨‍🎓 STUDENT</span>
                        <div style="display: flex; gap: 8px;">
                            <span class="badge-pill">{mode_badge}</span>
                            <span class="badge-pill">⏱️ {ts}</span>
                        </div>
                    </div>
                    <p class="chat-text">"{content}"</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            lat = f"{msg.get('latency_ms', 0):.0f}ms" if msg.get("latency_ms") else "<1s"
            st.markdown(
                f"""
                <div class="chat-line-assistant">
                    <div class="speaker-meta">
                        <span class="speaker-tag speaker-tag-assistant">🎓 SENIOR TUTOR</span>
                        <div style="display: flex; gap: 8px;">
                            <span class="badge-pill">⚡ {lat}</span>
                            <span class="badge-pill">🗣️ {st.session_state.voice_name.capitalize()}</span>
                            <span class="badge-pill">⏱️ {ts}</span>
                        </div>
                    </div>
                    <p class="chat-text">{content}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if msg.get("audio_bytes"):
                st.audio(msg["audio_bytes"], format="audio/mp3", autoplay=(idx == len(st.session_state.messages) - 1))

            tools = msg.get("tool_calls", [])
            if tools:
                for tc in tools:
                    t_name = tc.get("tool", "")
                    t_args = tc.get("args", {})
                    t_res = tc.get("result", {})

                    if t_name == "open_app" and t_res.get("url"):
                        t_label = t_res.get("target", "Application")
                        t_url = t_res.get("url")
                        st.markdown(
                            f"""
                            <div class="tool-action-card">
                                <div>🚀 <strong>Auto-Launching {t_label}:</strong> <code>{t_args.get('query') or t_label}</code></div>
                                <a href="{t_url}" target="_blank" class="tool-link-btn">Open {t_label} in New Tab ↗</a>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        # Automatically open new tab in user's browser
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
                            <div class="tool-action-card">
                                <div>🧮 <strong>Math Calculation:</strong> <code>{t_args.get('expression')}</code></div>
                                <span class="badge-pill" style="font-size: 13px; font-weight: bold; color: #38bdf8;">= {t_res.get('formatted', t_res.get('result'))}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

    user_chat = st.chat_input("Ask a doubt, formula derivation, or concept to Senior Tutor...")
    if user_chat:
        execute_turn(user_chat, input_mode="text")
        st.rerun()


# =========================================================================== #
# MODULE 2: Crash Course Planner
# =========================================================================== #
elif st.session_state.active_tab == "Crash Course Planner":
    st.markdown("### 📅 Fast-Track Crash Course & Exam Revision Planner")
    st.caption("Generate an optimized day-by-day study roadmap tailored to your remaining preparation time.")

    col1, col2 = st.columns(2)
    with col1:
        subject = st.text_input("Subject / Course Name:", value="Data Structures & Algorithms")
        days_left = st.selectbox(
            "Time Remaining Until Exam:",
            options=["3 Days (Emergency Sprint)", "7 Days (1 Week Fast-Track)", "14 Days (Balanced Revision)", "30 Days (Full Mastery)"]
        )
    with col2:
        hours_per_day = st.slider("Daily Study Hours Available:", min_value=1, max_value=12, value=4)
        target_score = st.selectbox(
            "Target Goal:",
            options=["Score 90%+ (Top Grade)", "Pass Comfortably (75%+)", "High-Yield Topics Only"]
        )

    if st.button("🚀 Generate Crash Course Study Plan", type="primary", use_container_width=True):
        sys_role = "You are an elite Senior Academic Tutor and Exam Strategist. Create concise, actionable, high-yield study timetables that maximize score retention."
        user_prompt = f"""Create a day-by-day crash course study timetable for:
- Subject: {subject}
- Time Horizon: {days_left}
- Available Hours: {hours_per_day} hours/day
- Target Goal: {target_score}

Structure the plan with:
1. High-Yield Priority Matrix (Must-know 80/20 topics)
2. Day-by-day schedule with Morning, Afternoon, and Evening study blocks
3. Daily formula & concept checkpoint
4. Final day mock test & exam strategy checklist"""

        with st.spinner("Senior Tutor is structuring your personalized study roadmap..."):
            plan_text = generate_tutor_response(user_prompt, sys_role)
            st.session_state["latest_study_plan"] = plan_text

    if "latest_study_plan" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state["latest_study_plan"])

        col_save, col_down = st.columns(2)
        with col_save:
            if st.button("📋 Save Milestones as Study Tasks in SQLite", use_container_width=True):
                db_add_task(title=f"Review High-Yield topics for {subject}")
                db_add_task(title=f"Practice 10 mock questions for {subject}")
                st.success("Study tasks successfully saved to your revision task list!")
        with col_down:
            st.download_button(
                label="📥 Download Study Plan (.md)",
                data=st.session_state["latest_study_plan"],
                file_name=f"{subject.replace(' ', '_').lower()}_study_plan.md",
                mime="text/markdown",
                use_container_width=True,
            )


# =========================================================================== #
# MODULE 3: High-Yield Important Topics
# =========================================================================== #
elif st.session_state.active_tab == "High-Yield Important Topics":
    st.markdown("### 🎯 High-Yield Exam Topics & Formula Cheat Sheet")
    st.caption("Identify 80/20 topics that carry the highest marks in examinations, along with essential formulas and common exam traps.")

    st.markdown("**⚡ Quick Subject Presets:**")
    preset_cols = st.columns(5)
    presets = [
        "Data Structures & Algorithms",
        "Database Management (DBMS)",
        "Operating Systems",
        "Engineering Mathematics",
        "Engineering Physics",
    ]
    for i, pre in enumerate(presets):
        with preset_cols[i]:
            if st.button(pre, key=f"pre_{i}", use_container_width=True):
                st.session_state["hy_sub_val"] = pre
                st.rerun()

    default_sub = st.session_state.get("hy_sub_val", "Data Structures & Algorithms")

    col_sub, col_unit = st.columns(2)
    with col_sub:
        hy_subject = st.text_input("Subject:", value=default_sub)
    with col_unit:
        hy_unit = st.text_input("Specific Topic or Entire Syllabus:", value="Trees, Graphs, and Dynamic Programming")

    if st.button("⚡ Extract High-Yield Topics & Cheat Sheet", type="primary", use_container_width=True):
        sys_role = "You are a master academic professor. Extract the highest probability exam questions, essential formulas, and key pitfalls."
        p = f"""Analyze the subject '{hy_subject}' and topic '{hy_unit}'. Provide:
1. Top 5 High-Yield Topics (ranked by mark weightage in typical semester/board exams)
2. Essential Formulas & Theorems (with clear KaTeX notation)
3. Common Exam Traps & Pitfalls (where students lose marks and how to avoid them)
4. 3 Most Frequently Repeated Exam Questions with quick answering tips."""

        with st.spinner("Analyzing high-yield exam patterns..."):
            hy_result = generate_tutor_response(p, sys_role)
            st.session_state["latest_hy"] = hy_result

    if "latest_hy" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state["latest_hy"])

        if st.button("💾 Save to Revision Notes Archive", use_container_width=True):
            db_add_note(text=st.session_state["latest_hy"][:500], tags=hy_subject)
            st.success("Saved to your Notes Archive in SQLite!")


# =========================================================================== #
# MODULE 4: Practice Quiz & Evaluation
# =========================================================================== #
elif st.session_state.active_tab == "Practice Quiz & Evaluation":
    st.markdown("### 📝 Interactive Practice Quiz & Self-Evaluation")
    st.caption("Test your exam readiness with dynamic questions, instant feedback, and benchmark diagnostics.")

    col_q1, col_q2, col_q3 = st.columns(3)
    with col_q1:
        quiz_subject = st.text_input("Quiz Topic / Subject:", value="Data Structures & Algorithms")
    with col_q2:
        num_q = st.selectbox("Number of Questions:", options=[3, 5])
    with col_q3:
        difficulty = st.selectbox("Difficulty Level:", options=["Standard Exam", "Challenging (Distinction)", "Concept Mastery"])

    if st.button("🚀 Generate Practice Quiz", type="primary", use_container_width=True):
        sys_role = "You are an exam examiner. Return ONLY a valid JSON array of multiple choice questions."
        p = f"""Generate a {num_q}-question multiple choice quiz on '{quiz_subject}' at difficulty '{difficulty}'.
Return ONLY valid JSON matching this schema:
[
  {{
    "id": 1,
    "question": "Question text here?",
    "options": ["A) option 1", "B) option 2", "C) option 3", "D) option 4"],
    "correct_index": 0,
    "explanation": "Why this is correct."
  }}
]"""
        with st.spinner("Generating quiz questions..."):
            raw_json = generate_tutor_response(p, sys_role)
            try:
                # Clean code fences
                clean_j = raw_json.replace("```json", "").replace("```", "").strip()
                quiz_data = json.loads(clean_j)
                st.session_state.active_quiz = quiz_data
                st.session_state.quiz_submitted = False
            except Exception as e:
                # Fallback high quality quiz
                st.session_state.active_quiz = [
                    {
                        "id": 1,
                        "question": "What is the time complexity of searching in a balanced Binary Search Tree (AVL / Red-Black Tree)?",
                        "options": ["A) O(1)", "B) O(log n)", "C) O(n)", "D) O(n log n)"],
                        "correct_index": 1,
                        "explanation": "A balanced BST guarantees tree height of O(log n), making search, insertion, and deletion strictly O(log n).",
                    },
                    {
                        "id": 2,
                        "question": "Which Python data structure provides O(1) average time complexity for key lookups?",
                        "options": ["A) List", "B) Tuple", "C) Dictionary / Set", "D) Linked List"],
                        "correct_index": 2,
                        "explanation": "Dictionaries and sets in Python are implemented using hash tables with O(1) average lookup time.",
                    },
                    {
                        "id": 3,
                        "question": "Which sorting algorithm is guaranteed to be stable and runs in O(n log n) worst-case time?",
                        "options": ["A) QuickSort", "B) MergeSort", "C) HeapSort", "D) SelectionSort"],
                        "correct_index": 1,
                        "explanation": "MergeSort is both stable (preserves relative order of duplicate keys) and has O(n log n) worst-case time complexity.",
                    },
                ]
                st.session_state.quiz_submitted = False

    if st.session_state.active_quiz:
        st.markdown("---")
        st.markdown("#### ✍️ Answer the Questions Below:")
        user_answers = {}

        for q in st.session_state.active_quiz:
            q_id = q["id"]
            st.markdown(f"**Q{q_id}. {q['question']}**")
            user_answers[q_id] = st.radio(
                f"Select answer for Q{q_id}:",
                options=q["options"],
                key=f"quiz_opt_{q_id}",
                label_visibility="collapsed",
            )
            st.markdown("")

        if st.button("📊 Submit Quiz for Evaluation", type="primary", use_container_width=True):
            st.session_state.quiz_submitted = True
            st.session_state.user_answers = user_answers

        if st.session_state.get("quiz_submitted"):
            st.markdown("---")
            st.markdown("### 🏆 Quiz Evaluation Scorecard")
            correct_count = 0
            total_q = len(st.session_state.active_quiz)

            for q in st.session_state.active_quiz:
                q_id = q["id"]
                chosen_opt = st.session_state.user_answers.get(q_id, "")
                correct_opt = q["options"][q["correct_index"]]
                is_correct = chosen_opt == correct_opt

                if is_correct:
                    correct_count += 1
                    st.success(f"✅ **Q{q_id}: Correct!** You selected: `{chosen_opt}`\n\n💡 *{q['explanation']}*")
                else:
                    st.error(f"❌ **Q{q_id}: Incorrect.** You selected: `{chosen_opt}` | Correct Answer: **{correct_opt}**\n\n💡 *{q['explanation']}*")

            score_pct = round((correct_count / total_q) * 100, 1)
            grade = "A+ (Outstanding!)" if score_pct >= 90 else ("B (Good Work)" if score_pct >= 70 else "Needs Revision")
            st.metric("Total Score", f"{score_pct}%", f"{correct_count}/{total_q} Correct • {grade}")

    st.markdown("---")
    # Collapsible System Benchmark Runner
    with st.expander("⚡ Run System Benchmark & Error Detection Engine", expanded=False):
        st.caption("Probe tool execution latencies, accuracy, error resilience, and safety confirmation gating.")
        if st.button("🚀 Run Live System Benchmark Probe"):
            with st.spinner("Benchmarking engines..."):
                b_res = run_comprehensive_benchmark()
                st.session_state.benchmark_results = b_res
                st.success(f"Benchmark Complete! Overall Score: {b_res['overall_score']}% PASS")
        if st.session_state.benchmark_results:
            b = st.session_state.benchmark_results
            col_b1, col_b2, col_b3 = st.columns(3)
            col_b1.metric("Overall Score", f"{b['overall_score']}%")
            col_b2.metric("Tool Accuracy", f"{b['accuracy']['accuracy_pct']}%")
            col_b3.metric("Error Resilience", f"{b['error_resilience']['resilience_pct']}%")
            st.bar_chart({k: v["avg_ms"] for k, v in b["latencies"].items()})


# =========================================================================== #
# MODULE 5: Past Papers Archive
# =========================================================================== #
elif st.session_state.active_tab == "Past Papers Archive":
    st.markdown("### 📚 Past Exam Papers & Revision Notes Archive")
    st.caption("Search past exam papers, review step-by-step solved questions, and access your saved study notes.")

    col_search, col_btn = st.columns([3, 1])
    with col_search:
        paper_query = st.text_input("Search Past Papers / Question Bank:", value="Calculus Integration Techniques")
    with col_btn:
        st.write("")
        st.write("")
        search_btn = st.button("🔍 Search Archive", use_container_width=True)

    if search_btn or paper_query:
        # Check SQLite paper store first
        paper_chunks = db_search_paper_chunks(paper_query, top_k=3)
        if paper_chunks:
            st.markdown("#### 📄 Matching Past Paper Sections Found:")
            for p in paper_chunks:
                st.markdown(f"""
                <div class="study-card">
                    <h4>📄 {p.get('paper_title', 'Exam Paper')} (Section {p.get('section', 'General')})</h4>
                    <p>{p.get('text', '')[:300]}...</p>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info(f"No direct PDF chunks found for '{paper_query}'. Asking Senior Tutor for standard past year questions...")
            p_prompt = f"Provide 2 typical past year exam questions on '{paper_query}' with complete step-by-step verified solutions and marking scheme breakdown."
            with st.spinner("Senior Tutor is fetching past exam questions & solutions..."):
                sol_text = generate_tutor_response(p_prompt, "You are a senior university examiner.")
                st.markdown(sol_text)

    st.markdown("---")
    st.markdown("#### 📝 Saved Revision Notes in SQLite Database")
    notes = db_list_notes()
    if notes:
        for n in notes[:5]:
            st.markdown(f"""
            <div class="study-card">
                <span class="badge-pill" style="color: #38bdf8;">🏷️ {n.get('tags') or 'General Note'}</span>
                <p style="margin-top: 8px; font-size: 14px;">{n.get('text')}</p>
                <span style="font-size: 11px; color: #64748b;">Created: {n.get('created_at')}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("No revision notes stored yet. Use the 'High-Yield Topics' tab to save notes.")
