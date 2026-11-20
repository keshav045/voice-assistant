"""Nexus AI Senior Tutor & Exam Suite — Streamlit Web & Cloud Application.
ChatGPT-style Minimalist UI with Real-Time Line-by-Line Voice Conversation & Study Suite.
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
# Streamlit Page Setup & Custom Styling (ChatGPT Aesthetic)
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Senior Tutor — ChatGPT Edition",
    page_icon="🎓",
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

    /* Top Horizontal Module Tabs */
    .module-nav-wrap {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 4px 0 16px 0;
        margin-bottom: 20px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        overflow-x: auto;
    }

    /* ChatGPT Centered Welcome Screen */
    .chatgpt-center-hero {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        margin-top: 50px;
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
        color: #b4b4b4;
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
        margin-bottom: 32px;
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

    /* ChatGPT Pill Input Styling */
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

    /* Voice Mode Compact Bar */
    .voice-strip {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 18px;
        background: #1a1a1a;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        margin-bottom: 16px;
    }

    /* Generic Study Cards */
    .study-card {
        background: #282828;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 22px 26px;
        margin-bottom: 20px;
        color: #ececec;
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

    with st.spinner("Thinking..."):
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
    """Generate academic output using OpenAI GPT-4o or Local Ollama."""
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
    return f"Prepared analysis for: {prompt}\n\nPlease review key concepts and formulas in your textbook."


# --------------------------------------------------------------------------- #
# STUDENT SIDEBAR: Clean, Focused Navigation Menu (ChatGPT Style)
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 24px; padding: 4px;">
            <div style="font-size: 22px; background: #2f2f2f; width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255,255,255,0.1);">🎓</div>
            <div>
                <h3 style="margin: 0; font-size: 16px; font-weight: 700; color: #ececec;">Senior Tutor</h3>
                <p style="margin: 0; font-size: 11px; color: #9ca3af;">Academic AI Suite</p>
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
        "NAVIGATION",
        options=MODULE_NAMES,
        index=MODULE_NAMES.index(st.session_state.active_tab),
        key="sidebar_module_radio",
    )
    if selected_sidebar_tab != st.session_state.active_tab:
        st.session_state.active_tab = selected_sidebar_tab
        st.rerun()

    st.markdown("---")
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
    model_mode = st.radio(
        "Engine:",
        options=["☁️ OpenAI GPT-4o", "🖥️ Local Ollama"],
        index=0 if not os.environ.get("OPENAI_BASE_URL") else 1,
    )
    if "Local" in model_mode:
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
        st.caption("Using Cloud OpenAI GPT-4o")

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


# --------------------------------------------------------------------------- #
# Top Horizontal Navigation Tabs (Matches Screenshot 1 & ChatGPT Style)
# --------------------------------------------------------------------------- #
top_cols = st.columns(5)
for i, m_name in enumerate(MODULE_NAMES):
    with top_cols[i]:
        is_active = (m_name == st.session_state.active_tab)
        btn_type = "primary" if is_active else "secondary"
        if st.button(m_name, key=f"nav_top_{i}", type=btn_type, use_container_width=True):
            st.session_state.active_tab = m_name
            st.rerun()


# =========================================================================== #
# MODULE 1: Senior Tutor Chat (ChatGPT Design Matching Image 2)
# =========================================================================== #
if st.session_state.active_tab == "Senior Tutor Chat":

    # ChatGPT Centered Welcome Screen (When no messages yet)
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="chatgpt-center-hero">
                <h1 class="chatgpt-title">What’s on your mind today?</h1>
                <p class="chatgpt-sub">Ask Senior Tutor any university question, formula derivation, or exam strategy.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 4 Prompt Suggestions (2x2 Grid like ChatGPT)
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            if st.button("⚡ Explain QuickSort vs MergeSort\n\nCompare step-by-step with time complexities", key="sug_1", use_container_width=True):
                execute_turn("Explain QuickSort vs MergeSort step by step with time complexities", input_mode="text")
                st.rerun()
            if st.button("🧮 Solve: integral of x * e^(2x) dx\n\nShow complete integration by parts steps", key="sug_2", use_container_width=True):
                execute_turn("Solve: integral of x * e^(2x) dx step by step", input_mode="text")
                st.rerun()
        with p_col2:
            if st.button("🔬 What are the 3 laws of Thermodynamics?\n\nExplain with practical engineering examples", key="sug_3", use_container_width=True):
                execute_turn("What are the 3 laws of Thermodynamics with practical examples?", input_mode="text")
                st.rerun()
            if st.button("📋 Create a 7-day crash study roadmap\n\nFor high-yield exam preparation", key="sug_4", use_container_width=True):
                execute_turn("Create a 7-day crash study roadmap for my upcoming exams", input_mode="text")
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
                        <div class="chatgpt-avatar-icon">🎓</div>
                        <span class="chatgpt-author-name">Senior Tutor</span>
                        <span class="chatgpt-latency-pill">{lat}</span>
                        <span class="chatgpt-latency-pill">{ts}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Render markdown with KaTeX math cleanly
            st.markdown(content)

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

    # Sleek Compact Voice Mode Option (Positioned discreetly above input)
    with st.expander("🎙️ Voice Mode (Click here to speak to Senior Tutor)", expanded=False):
        audio_input_data = st.audio_input("Speak your question:")
        if audio_input_data is not None:
            audio_bytes = audio_input_data.read()
            audio_hash = hash(audio_bytes)
            if st.session_state.last_processed_audio != audio_hash:
                st.session_state.last_processed_audio = audio_hash
                with st.spinner("Transcribing speech..."):
                    transcribed_text = transcribe_uploaded_audio(audio_bytes)
                    if transcribed_text:
                        execute_turn(transcribed_text, input_mode="voice")
                        st.rerun()
                    else:
                        st.warning("Could not detect clear speech. Please speak again.")

    # ChatGPT Capsule Input Bar (Matches Image 2)
    user_chat = st.chat_input("Ask Senior Tutor anything...")
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

        with st.spinner("Structuring your personalized study roadmap..."):
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
            with st.spinner("Fetching past exam questions & solutions..."):
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
