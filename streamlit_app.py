"""Nexus AI Personal Voice Assistant — Streamlit Web & Cloud Application.
Real-Time Line-by-Line Voice Conversation, Benchmark Evaluation & Error Detection Engine.
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
    db_delete_chat_session,
    db_get_user_oauth,
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
    page_title="Nexus AI Voice Assistant",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Global Base */
    .stApp {
        background-color: #080d1a;
        color: #f1f5f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Header Container */
    .nexus-hero {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 18px 24px;
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.9));
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 16px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    }
    .nexus-title-wrap {
        display: flex;
        align-items: center;
        gap: 16px;
    }
    .nexus-orb-glow {
        width: 50px;
        height: 50px;
        border-radius: 16px;
        background: linear-gradient(135deg, #6366f1, #a855f7);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 26px;
        box-shadow: 0 0 24px rgba(99, 102, 241, 0.6);
        animation: pulseOrb 2.5s infinite alternate ease-in-out;
    }
    @keyframes pulseOrb {
        0% { transform: scale(1); box-shadow: 0 0 16px rgba(99, 102, 241, 0.4); }
        100% { transform: scale(1.06); box-shadow: 0 0 32px rgba(168, 85, 247, 0.8); }
    }
    .nexus-h1 {
        font-size: 24px;
        font-weight: 700;
        margin: 0;
        background: linear-gradient(90deg, #f8fafc, #c7d2fe);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .nexus-sub {
        font-size: 13px;
        color: #94a3b8;
        margin: 0;
    }

    /* Animated Waveform Visualizer Banner */
    .waveform-bar-box {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px;
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(99, 102, 241, 0.3);
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
        font-size: 12px;
        font-weight: 600;
        color: #38bdf8;
        margin-left: 8px;
        letter-spacing: 0.5px;
    }

    /* Line-by-Line Conversation Styling */
    .chat-line-container {
        margin-bottom: 20px;
    }
    .chat-line-user {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-left: 4px solid #6366f1;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .chat-line-assistant {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(16, 185, 129, 0.2);
        border-left: 4px solid #10b981;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }
    .speaker-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
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
        gap: 4px;
        font-size: 11px;
        padding: 2px 8px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.08);
        color: #cbd5e1;
    }
    .chat-text {
        font-size: 15px;
        line-height: 1.6;
        color: #f1f5f9;
        margin: 0;
    }

    /* Tool Action Cards */
    .tool-action-card {
        margin-top: 10px;
        padding: 10px 14px;
        background: rgba(2, 6, 23, 0.6);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 8px;
    }
    .tool-link-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        color: #ffffff !important;
        font-weight: 600;
        font-size: 12px;
        border-radius: 8px;
        text-decoration: none !important;
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.4);
    }
    .tool-link-btn:hover {
        background: linear-gradient(135deg, #6366f1, #9333ea);
    }
    .tool-link-whatsapp {
        background: linear-gradient(135deg, #16a34a, #15803d) !important;
        box-shadow: 0 2px 8px rgba(22, 163, 74, 0.4) !important;
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
    # Load past turns for current session if exists in database
    existing_turns = db_get_session_turns(user_id="guest", session_id=st.session_state.session_id)
    for t in existing_turns:
        st.session_state.messages.append({
            "role": "user",
            "content": t["user_message"],
            "timestamp": t.get("created_at", datetime.now(timezone.utc).strftime("%I:%M %p")),
            "input_mode": "voice",
        })
        st.session_state.messages.append({
            "role": "assistant",
            "content": t["spoken_reply"],
            "tool_calls": json.loads(t["tool_calls"]) if isinstance(t.get("tool_calls"), str) else (t.get("tool_calls") or []),
            "latency_ms": t.get("latency_ms", 0.0),
            "timestamp": t.get("created_at", datetime.now(timezone.utc).strftime("%I:%M %p")),
        })

if "auto_speech" not in st.session_state:
    st.session_state.auto_speech = True

if "voice_name" not in st.session_state:
    st.session_state.voice_name = "alloy"

if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = None

if "benchmark_results" not in st.session_state:
    st.session_state.benchmark_results = None


# --------------------------------------------------------------------------- #
# Helper Functions: Whisper STT & OpenAI TTS
# --------------------------------------------------------------------------- #
def transcribe_uploaded_audio(audio_data: bytes) -> str:
    """Send voice audio recording to OpenAI Whisper API."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key or openai_key.startswith("your-"):
        logger.warning("OPENAI_API_KEY is not configured.")
        return ""

    try:
        client = OpenAI(api_key=openai_key)
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


def synthesize_speech(text: str, voice: str = "alloy") -> bytes:
    """Convert agent spoken text response to MP3 audio via OpenAI TTS."""
    clean_text = clean_spoken_text(text)
    if not clean_text:
        return b""

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key or openai_key.startswith("your-"):
        return b""

    try:
        client = OpenAI(api_key=openai_key)
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=clean_text[:4096],
            speed=1.0,
            response_format="mp3",
        )
        return response.content
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        return b""


def execute_turn(user_prompt: str, input_mode: str = "voice"):
    """Run full agent turn, save history, and update UI state."""
    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        return

    now_str = datetime.now(timezone.utc).strftime("%I:%M %p")

    # Add user message line to UI
    st.session_state.messages.append({
        "role": "user",
        "content": clean_prompt,
        "timestamp": now_str,
        "input_mode": input_mode,
    })

    # Execute agent pipeline via asyncio
    with st.spinner("Nexus AI is reasoning & dispatching tools..."):
        try:
            result = asyncio.run(process_user_turn(
                user_text=clean_prompt,
                session_id=st.session_state.session_id,
                user_id="guest",
            ))
        except Exception as err:
            result = {
                "spoken_reply": f"An error occurred while processing: {err}",
                "tool_calls_executed": [],
                "requires_confirmation": False,
                "latency_ms": 0.0,
            }

    spoken_reply = result.get("spoken_reply", "")
    tool_calls = result.get("tool_calls_executed", [])
    requires_confirm = result.get("requires_confirmation", False)
    confirm_q = result.get("confirmation_question")
    latency_ms = result.get("latency_ms", 0.0)

    # Generate TTS audio if enabled
    audio_bytes = None
    if st.session_state.auto_speech and spoken_reply:
        audio_bytes = synthesize_speech(spoken_reply, voice=st.session_state.voice_name)

    # Save assistant message in UI state
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

    # Persist in database
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
# Sidebar: System Status & Controls
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🎙️ Nexus Control Hub")
    st.caption("Active Session: `" + st.session_state.session_id + "`")
    st.markdown("---")

    # Cloud Connection Status Probes
    openai_key_val = os.environ.get("OPENAI_API_KEY", "")
    openai_ok = bool(openai_key_val and not openai_key_val.startswith("your-") and len(openai_key_val) > 20)
    livekit_url_val = os.environ.get("LIVEKIT_URL", "")
    livekit_ok = bool(livekit_url_val and os.environ.get("LIVEKIT_API_KEY"))
    oauth_record = db_get_user_oauth(user_id="guest", provider="google")
    gmail_connected = bool(oauth_record and oauth_record.get("access_token"))

    st.markdown(
        f"""
        <div style="background: rgba(15, 23, 42, 0.6); padding: 12px; border-radius: 10px; border: 1px solid rgba(51, 65, 85, 0.6); font-size: 13px;">
            <div style="margin-bottom: 6px;">
                {'🟢' if openai_ok else '🔴'} <strong>OpenAI Engine:</strong> <code>{OPENAI_MODEL}</code>
            </div>
            <div style="margin-bottom: 6px;">
                {'🟢' if livekit_ok else '🟡'} <strong>LiveKit WebRTC:</strong> <code>{'Connected' if livekit_ok else 'Local'}</code>
            </div>
            <div style="margin-bottom: 6px;">
                {'🟢' if gmail_connected else '🟡'} <strong>Gmail OAuth:</strong> <code>{'Authenticated' if gmail_connected else 'SMTP Fallback'}</code>
            </div>
            <div>
                🟢 <strong>SQLite Concurrency:</strong> <code>WAL Active</code>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("#### 🔊 Audio & Voice Settings")
    st.session_state.auto_speech = st.toggle("Auto-Play Spoken Response", value=st.session_state.auto_speech)
    st.session_state.voice_name = st.selectbox(
        "OpenAI Voice Persona",
        options=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        index=["alloy", "echo", "fable", "onyx", "nova", "shimmer"].index(st.session_state.voice_name),
    )

    st.markdown("---")
    st.markdown("#### 💬 Conversation History")
    sessions = db_list_chat_sessions(user_id="guest", limit=20)
    session_options = [s["session_id"] for s in sessions]
    if st.session_state.session_id not in session_options:
        session_options.insert(0, st.session_state.session_id)

    selected_sess = st.selectbox(
        "Switch Session",
        options=session_options,
        index=session_options.index(st.session_state.session_id),
    )
    if selected_sess != st.session_state.session_id:
        st.session_state.session_id = selected_sess
        st.session_state.messages = []
        existing = db_get_session_turns(user_id="guest", session_id=selected_sess)
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
                "tool_calls": json.loads(t["tool_calls"]) if isinstance(t.get("tool_calls"), str) else (t.get("tool_calls") or []),
                "latency_ms": t.get("latency_ms", 0.0),
                "timestamp": t.get("created_at", "Past"),
            })
        st.rerun()

    if st.button("🗑️ Clear Current History", use_container_width=True):
        db_clear_chat_history(user_id="guest", session_id=st.session_state.session_id)
        st.session_state.messages = []
        st.success("History cleared.")
        st.rerun()


# --------------------------------------------------------------------------- #
# Main Content Area: Top Header Hero
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="nexus-hero">
        <div class="nexus-title-wrap">
            <div class="nexus-orb-glow">🎙️</div>
            <div>
                <h1 class="nexus-h1">Nexus AI Voice Assistant</h1>
                <p class="nexus-sub">Real-Time Voice Intelligence • Line-by-Line Conversation • Full Evaluation Suite</p>
            </div>
        </div>
        <div class="waveform-bar-box">
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <div class="wave-line"></div>
            <span class="status-text">LISTENING & SPEAKING</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Primary Tabs: Voice Assistant, Benchmark & Eval, Tools Sandbox, Transcript
# --------------------------------------------------------------------------- #
tab_voice, tab_bench, tab_tools, tab_transcript = st.tabs([
    "🎙️ Voice Assistant",
    "📊 Benchmark & Evaluation",
    "🛠️ Live Tools Sandbox",
    "📜 Session Transcript",
])


# =========================================================================== #
# TAB 1: Voice Assistant (Line-by-Line Conversation Interface)
# =========================================================================== #
with tab_voice:
    # Voice Input Station
    st.markdown("#### 🎤 Voice Recording Station")
    col_mic, col_tips = st.columns([2, 1])

    with col_mic:
        audio_input_data = st.audio_input("Click the microphone to speak your command:")
        if audio_input_data is not None:
            audio_bytes = audio_input_data.read()
            audio_hash = hash(audio_bytes)
            if st.session_state.last_processed_audio != audio_hash:
                st.session_state.last_processed_audio = audio_hash
                with st.spinner("Transcribing speech via OpenAI Whisper..."):
                    transcribed_text = transcribe_uploaded_audio(audio_bytes)
                    if transcribed_text:
                        execute_turn(transcribed_text, input_mode="voice")
                        st.rerun()
                    else:
                        st.warning("Could not detect clear speech. Please speak again.")

    with col_tips:
        st.markdown("**Quick Voice Commands:**")
        sample_chips = [
            "What is 25 * 40 + 15% of 1000?",
            "What time is it in Tokyo right now?",
            "Open YouTube and search lo-fi music",
            "Send WhatsApp message to Rahul saying hello",
            "Search latest news about AI voice agents",
        ]
        for chip in sample_chips:
            if st.button(f"🗣️ {chip}", key=f"chip_{chip[:15]}", use_container_width=True):
                execute_turn(chip, input_mode="text")
                st.rerun()

    st.markdown("---")
    st.markdown("### 💬 Line-by-Line Conversation")

    if not st.session_state.messages:
        st.markdown(
            """
            <div style="text-align: center; padding: 40px 20px; color: #64748b; background: rgba(15, 23, 42, 0.4); border-radius: 16px; border: 1px dashed rgba(99, 102, 241, 0.3);">
                <div style="font-size: 42px; margin-bottom: 12px;">👋 🎙️</div>
                <h3 style="color: #cbd5e1; font-weight: 600;">Welcome to Nexus Voice Assistant</h3>
                <p style="font-size: 14px;">Record your voice above, type a command below, or click any prompt chip to start speaking!</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Render Dialogue Line-by-Line
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
                        <span class="speaker-tag speaker-tag-user">🗣️ YOU</span>
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
                        <span class="speaker-tag speaker-tag-assistant">🤖 NEXUS VOICE</span>
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

            # Audio Player for spoken response
            if msg.get("audio_bytes"):
                st.audio(msg["audio_bytes"], format="audio/mp3", autoplay=(idx == len(st.session_state.messages) - 1))

            # Executed Tool Cards
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
                                <div>🚀 <strong>App Launcher:</strong> Resolved target <code>{t_label}</code></div>
                                <a href="{t_url}" target="_blank" class="tool-link-btn">Launch {t_label} in New Tab ↗</a>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    elif t_name == "send_whatsapp_message" and t_res.get("url"):
                        c_target = t_res.get("contact", "Contact")
                        w_url = t_res.get("url")
                        st.markdown(
                            f"""
                            <div class="tool-action-card">
                                <div>💬 <strong>WhatsApp Messenger:</strong> Ready for <code>{c_target}</code></div>
                                <a href="{w_url}" target="_blank" class="tool-link-btn tool-link-whatsapp">Open WhatsApp Web Chat ↗</a>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    elif t_name == "calculator" and t_res.get("success"):
                        st.markdown(
                            f"""
                            <div class="tool-action-card">
                                <div>🧮 <strong>Math Calculated:</strong> <code>{t_args.get('expression')}</code></div>
                                <span class="badge-pill" style="font-size: 13px; font-weight: bold; color: #38bdf8;">= {t_res.get('formatted', t_res.get('result'))}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    elif t_name == "send_email" and t_res.get("success"):
                        st.markdown(
                            f"""
                            <div class="tool-action-card">
                                <div>✉️ <strong>Email Dispatched:</strong> To: <code>{t_res.get('to')}</code> | Subj: <em>"{t_res.get('subject')}"</em></div>
                                <span class="badge-pill" style="color: #6ee7b7;">Delivered via {t_res.get('from', 'Gmail')}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with st.expander(f"🛠️ View Raw Tool Execution: `{t_name}`", expanded=False):
                        st.json({"tool": t_name, "arguments": t_args, "result": t_res})

            # Confirmation buttons if turn requires confirmation
            if msg.get("requires_confirmation") and idx == len(st.session_state.messages) - 1:
                st.warning(f"⚠️ {msg.get('confirmation_question', 'Confirmation required. Proceed?')}")
                c_btn1, c_btn2, _ = st.columns([1, 1, 3])
                with c_btn1:
                    if st.button("✅ Yes, Proceed", key=f"conf_yes_{idx}"):
                        execute_turn("yes", input_mode="text")
                        st.rerun()
                with c_btn2:
                    if st.button("❌ No, Cancel", key=f"conf_no_{idx}"):
                        execute_turn("no", input_mode="text")
                        st.rerun()

    # Chat Text Input
    user_chat = st.chat_input("Type a message or command (e.g. 'what time is it in Paris', 'open youtube', 'calculate 450 * 12')...")
    if user_chat:
        execute_turn(user_chat, input_mode="text")
        st.rerun()


# =========================================================================== #
# TAB 2: Benchmark & Evaluation (Error Detection & Performance Metrics)
# =========================================================================== #
with tab_bench:
    st.markdown("### 📊 System Evaluation, Error Detection & Benchmark Engine")
    st.caption("Complete 5-stage benchmark suite evaluating tool accuracy, error resilience, safety gating, and component latencies.")

    col_run, col_space = st.columns([1, 2])
    with col_run:
        run_benchmark_btn = st.button("🚀 Run Full System Benchmark & Error Detection", type="primary", use_container_width=True)

    if run_benchmark_btn or st.session_state.benchmark_results is None:
        if run_benchmark_btn:
            with st.spinner("Executing full benchmark suite & error injection probes..."):
                st.session_state.benchmark_results = run_comprehensive_benchmark()
                st.success("Benchmark completed successfully!")

    b_data = st.session_state.benchmark_results
    if b_data:
        # Scorecards KPI Row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Overall Compliance", f"{b_data['overall_score']}%", "100% Target")
        m2.metric("Tool Accuracy", f"{b_data['accuracy']['accuracy_pct']}%", f"{b_data['accuracy']['passed']}/{b_data['accuracy']['total']} Passed")
        m3.metric("Error Resilience", f"{b_data['error_resilience']['resilience_pct']}%", f"{b_data['error_resilience']['handled']}/{b_data['error_resilience']['total']} Handled")
        m4.metric("Safety Precision", f"{b_data['safety']['safety_gating_precision_pct']}%", "Write Protection")

        st.markdown("---")

        # Component Latencies
        st.markdown("#### ⚡ 1. Component Latency Profile (Milliseconds)")
        lat_dict = {k: v["avg_ms"] for k, v in b_data["latencies"].items()}
        col_l1, col_l2 = st.columns([1, 1])
        with col_l1:
            st.dataframe(
                [{"Engine": k, "Avg (ms)": v["avg_ms"], "Min (ms)": v["min_ms"], "Max (ms)": v["max_ms"]} for k, v in b_data["latencies"].items()],
                use_container_width=True,
            )
        with col_l2:
            st.bar_chart(lat_dict)

        st.markdown("---")

        # Error Detection & Resilience Table
        st.markdown("#### 🛡️ 2. Error Detection & Resilience Testing")
        st.caption("Verifies system stability when encountering division by zero, syntax errors, malicious code injections, unknown apps, and invalid timezones.")
        for case in b_data["error_resilience"]["cases"]:
            icon = "✅" if case["handled_gracefully"] else "❌"
            st.markdown(f"- **{icon} {case['test']}**: `{case['details']}`")

        st.markdown("---")

        # Tool Execution Accuracy
        st.markdown("#### 🎯 3. Tool Calling & Output Accuracy")
        for t in b_data["accuracy"]["tests"]:
            icon = "✅" if t["passed"] else "❌"
            st.markdown(f"- **{icon} {t['name']}**: `{t['details']}`")

        st.markdown("---")

        # Infrastructure Readiness
        st.markdown("#### 🏗️ 4. System & Cloud Infrastructure Probes")
        sr = b_data["system_readiness"]
        r1, r2, r3, r4, r5 = st.columns(5)
        r1.success("SQLite WAL: Active" if sr["sqlite_wal_mode"] else "WAL Inactive")
        r2.success("Tables: Intact" if sr["database_tables_intact"] else "Tables Missing")
        r3.success("OpenAI LLM: Ready" if sr["openai_llm_ready"] else "LLM Unconfigured")
        r4.success("Google OAuth: Ready" if sr["google_oauth_ready"] else "OAuth Fallback")
        r5.success("LiveKit WebRTC: Ready" if sr["livekit_cloud_ready"] else "LiveKit Local")

        st.markdown("---")
        # Export options
        md_content = generate_markdown_report(b_data)
        col_d1, col_d2, _ = st.columns([1, 1, 2])
        with col_d1:
            st.download_button(
                "📥 Download Markdown Report",
                data=md_content,
                file_name="benchmark_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col_d2:
            st.download_button(
                "📥 Download JSON Data",
                data=json.dumps(b_data, indent=2),
                file_name="benchmark_report.json",
                mime="application/json",
                use_container_width=True,
            )


# =========================================================================== #
# TAB 3: Live Tools Sandbox (Direct Interactive Testing)
# =========================================================================== #
with tab_tools:
    st.markdown("### 🛠️ Interactive Tool Sandbox & Diagnostics")
    st.caption("Test individual tools, inspect inputs/outputs, and verify live response formats.")

    tool_choice = st.selectbox(
        "Choose a Tool to Test:",
        options=[
            "🧮 Math Calculator",
            "⏰ World Clock & Timezone",
            "🚀 App & Website Launcher",
            "💬 WhatsApp Web Messenger",
            "🐍 Python Code Execution Sandbox",
            "🔍 Live Web Search",
            "✉️ Email Composer Engine",
        ],
    )

    if "Calculator" in tool_choice:
        expr = st.text_input("Math Expression:", value="450 * 12 + 18% of 5000 - sqrt(144)")
        if st.button("Calculate", type="primary"):
            res = TOOLS_REGISTRY["calculator"](expression=expr)
            st.json(res)

    elif "World Clock" in tool_choice:
        tz = st.selectbox("Select Timezone:", options=["Asia/Kolkata", "UTC", "America/New_York", "Europe/London", "Asia/Tokyo"])
        if st.button("Check Time", type="primary"):
            res = TOOLS_REGISTRY["get_current_time"](timezone_str=tz)
            st.json(res)

    elif "App & Website Launcher" in tool_choice:
        app_target = st.selectbox("Application:", options=["youtube", "whatsapp", "gmail", "linkedin", "github", "spotify", "google"])
        query_val = st.text_input("Optional Query:", value="lofi beats")
        if st.button("Resolve Launcher URL", type="primary"):
            res = TOOLS_REGISTRY["open_app"](target=app_target, query=query_val)
            st.json(res)
            if res.get("url"):
                st.markdown(f'<a href="{res["url"]}" target="_blank" class="tool-link-btn">Launch {app_target} in New Tab ↗</a>', unsafe_allow_html=True)

    elif "WhatsApp" in tool_choice:
        c_name = st.text_input("Contact Name:", value="Rahul")
        w_msg = st.text_input("Message Text:", value="Hey, let's sync up on the project tomorrow!")
        if st.button("Generate WhatsApp Link", type="primary"):
            res = TOOLS_REGISTRY["send_whatsapp_message"](contact_name=c_name, message=w_msg)
            st.json(res)
            if res.get("url"):
                st.markdown(f'<a href="{res["url"]}" target="_blank" class="tool-link-btn tool-link-whatsapp">Open WhatsApp Web Chat ↗</a>', unsafe_allow_html=True)

    elif "Python Code" in tool_choice:
        py_code = st.text_area("Python Code to Run:", value="print([x**2 for x in range(6)])\nprint('Done!')", height=120)
        if st.button("Run Python Code", type="primary"):
            res = TOOLS_REGISTRY["run_python_code"](code=py_code)
            st.json(res)

    elif "Web Search" in tool_choice:
        s_query = st.text_input("Search Query:", value="current weather in New Delhi")
        if st.button("Search Web", type="primary"):
            res = TOOLS_REGISTRY["web_search"](query=s_query)
            st.json(res)

    elif "Email Composer" in tool_choice:
        from agent.tools.email import _compose_email
        e_desc = st.text_input("Meeting / Email Intent:", value="Project review meeting on Thursday at 3 PM")
        e_rec = st.text_input("Recipient Name:", value="Alex")
        if st.button("Compose AI Email", type="primary"):
            res = _compose_email(description=e_desc, recipient_name=e_rec)
            st.json(res)


# =========================================================================== #
# TAB 4: Session Transcript & History Manager
# =========================================================================== #
with tab_transcript:
    st.markdown("### 📜 Session Transcript & History")
    st.caption("Inspect raw dialogue turns, view latency timestamps, and export session logs.")

    turns = db_get_session_turns(user_id="guest", session_id=st.session_state.session_id)
    if turns:
        st.dataframe(
            [{"Turn ID": t.get("id"), "Timestamp": t.get("created_at"), "User Prompt": t.get("user_message"), "Assistant Reply": t.get("spoken_reply"), "Latency (ms)": t.get("latency_ms")} for t in turns],
            use_container_width=True,
        )

        # Download Transcript as Markdown
        transcript_md = [f"# Transcript for Session: `{st.session_state.session_id}`\n"]
        for t in turns:
            transcript_md.append(f"### Turn: {t.get('created_at')}")
            transcript_md.append(f"**USER:** {t.get('user_message')}")
            transcript_md.append(f"**ASSISTANT:** {t.get('spoken_reply')}")
            if t.get("tool_calls"):
                transcript_md.append(f"```json\n{json.dumps(t.get('tool_calls'), indent=2)}\n```")
            transcript_md.append("---\n")

        st.download_button(
            "📥 Download Session Transcript (.md)",
            data="\n".join(transcript_md),
            file_name=f"transcript_{st.session_state.session_id}.md",
            mime="text/markdown",
        )
    else:
        st.info("No recorded turns in this session yet.")
