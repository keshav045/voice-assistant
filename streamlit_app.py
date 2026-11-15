"""Nexus AI Personal Voice Assistant — Streamlit Web & Cloud Application.
Full real-time voice, multimodal tool dispatch, Gmail OAuth, and conversational intelligence.
"""

import asyncio
import io
import json
import logging
import os
import sys
import uuid
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
try:
    from agent.voice import clean_spoken_text
except Exception:
    import re
    def clean_spoken_text(text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r"#+\s*", "", text)
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
        clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)
        clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
        clean = re.sub(r"https?://\S+", "", clean)
        clean = re.sub(r"[-*]\s+", "", clean)
        clean = re.sub(r"[^\w\s.,!?'\":-]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean
from db.models import (
    get_db_connection,
    db_list_chat_sessions,
    db_get_session_turns,
    db_save_chat_turn,
    db_clear_chat_history,
    db_delete_chat_session,
    db_get_user_oauth,
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
    /* Global Styles */
    .stApp {
        background-color: #0b0f19;
        color: #f1f5f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Brand Header */
    .nexus-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px 20px;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(168, 85, 247, 0.12));
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 16px;
        margin-bottom: 24px;
    }
    .nexus-logo {
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: linear-gradient(135deg, #6366f1, #a855f7);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
        box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
    }
    .nexus-title {
        font-size: 22px;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0;
        background: linear-gradient(90deg, #f8fafc, #c7d2fe);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .nexus-subtitle {
        font-size: 13px;
        color: #94a3b8;
        margin: 0;
    }
    
    /* Tool Execution Badges */
    .tool-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background: rgba(99, 102, 241, 0.15);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 8px;
        font-size: 12px;
        font-weight: 600;
        color: #a5b4fc;
        margin-top: 6px;
        margin-bottom: 6px;
    }
    .tool-badge-success {
        background: rgba(16, 185, 129, 0.15);
        border-color: rgba(16, 185, 129, 0.3);
        color: #6ee7b7;
    }
    
    /* Status indicators in sidebar */
    .status-card {
        padding: 10px 14px;
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(51, 65, 85, 0.8);
        border-radius: 10px;
        font-size: 12px;
        margin-bottom: 8px;
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
        st.session_state.messages.append({"role": "user", "content": t["user_message"]})
        st.session_state.messages.append({
            "role": "assistant",
            "content": t["spoken_reply"],
            "tool_calls": json.loads(t["tool_calls"]) if isinstance(t.get("tool_calls"), str) else (t.get("tool_calls") or []),
        })

if "auto_speech" not in st.session_state:
    st.session_state.auto_speech = True

if "voice_name" not in st.session_state:
    st.session_state.voice_name = "alloy"

if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = None

if "pending_confirmation" not in st.session_state:
    st.session_state.pending_confirmation = None


# --------------------------------------------------------------------------- #
# Audio & Speech Helper Functions
# --------------------------------------------------------------------------- #
def transcribe_uploaded_audio(audio_bytes: bytes) -> str:
    """Transcribe audio using OpenAI Whisper-1."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or api_key.startswith("your-"):
        st.warning("Please configure your OPENAI_API_KEY to enable voice transcription.")
        return ""

    try:
        client = OpenAI(api_key=api_key)
        audio_io = io.BytesIO(audio_bytes)
        audio_io.name = "recording.wav"
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_io,
            language="en",
        )
        return transcript.text.strip()
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        st.error(f"Speech transcription error: {e}")
        return ""


def synthesize_speech(text: str, voice: str = "alloy") -> bytes:
    """Generate high-fidelity MP3 speech using OpenAI TTS-1."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    clean = clean_spoken_text(text)
    if not clean or not api_key or api_key.startswith("your-"):
        return b""

    try:
        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=clean,
            response_format="mp3",
        )
        return response.content
    except Exception as e:
        logger.warning(f"TTS synthesis error: {e}")
        return b""


def execute_turn(user_prompt: str):
    """Run full agent turn, save history, and update UI state."""
    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        return

    # Add user message to UI
    st.session_state.messages.append({"role": "user", "content": clean_prompt})

    # Execute agent pipeline via asyncio
    with st.spinner("Nexus AI is thinking & reasoning..."):
        try:
            result = asyncio.run(process_user_turn(
                user_text=clean_prompt,
                session_id=st.session_state.session_id,
                user_id="guest",
            ))
        except Exception as err:
            result = {
                "spoken_reply": f"An error occurred while processing your request: {err}",
                "tool_calls_executed": [],
                "requires_confirmation": False,
            }

    spoken_reply = result.get("spoken_reply", "")
    tool_calls = result.get("tool_calls_executed", [])
    requires_confirm = result.get("requires_confirmation", False)
    confirm_q = result.get("confirmation_question")

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
            latency_ms=result.get("latency_ms", 0.0),
        )
    except Exception as db_err:
        logger.warning(f"Failed to persist chat turn: {db_err}")


# --------------------------------------------------------------------------- #
# Sidebar: System Status & Controls
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### 🎙️ Nexus Control Center")
    st.caption("AI Voice Assistant • Real-Time Engine")

    st.markdown("---")
    st.markdown("#### ⚡ System Status")

    # 1. OpenAI Model
    api_key_set = bool(os.environ.get("OPENAI_API_KEY", "") and not os.environ.get("OPENAI_API_KEY", "").startswith("your-"))
    st.markdown(f"""
    <div class="status-card">
        <strong>🧠 Core Model:</strong> {OPENAI_MODEL}<br>
        <span style="color: {'#10b981' if api_key_set else '#ef4444'};">
            ● {'Online & Ready' if api_key_set else 'API Key Missing'}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # 2. Google OAuth
    oauth_record = db_get_user_oauth(user_id="guest", provider="google")
    oauth_email = oauth_record.get("email") if oauth_record else None
    has_oauth_keys = bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))
    st.markdown(f"""
    <div class="status-card">
        <strong>✉️ Google Gmail OAuth:</strong><br>
        <span style="color: {'#10b981' if oauth_email else ('#f59e0b' if has_oauth_keys else '#94a3b8')};">
            ● {'Linked: ' + oauth_email if oauth_email else ('Configured (Ready to Link)' if has_oauth_keys else 'Not Configured')}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # 3. LiveKit WebRTC Cloud
    lk_url = os.environ.get("LIVEKIT_URL", "").strip()
    st.markdown(f"""
    <div class="status-card">
        <strong>🌐 LiveKit WebRTC Cloud:</strong><br>
        <span style="color: {'#10b981' if lk_url else '#94a3b8'};">
            ● {'Cloud Connected' if lk_url else 'Standby'}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # 4. Database
    st.markdown("""
    <div class="status-card">
        <strong>🗄️ Database Engine:</strong><br>
        <span style="color: #10b981;">● SQLite WAL Mode (Concurrent)</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 🔊 Voice Preferences")
    st.session_state.auto_speech = st.checkbox(
        "Auto-play Spoken Responses",
        value=st.session_state.auto_speech,
        help="Synthesizes voice audio for every answer using OpenAI TTS-1.",
    )
    st.session_state.voice_name = st.selectbox(
        "TTS Voice Character",
        options=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        index=0,
        help="Select the AI voice personality for speech synthesis.",
    )

    st.markdown("---")
    st.markdown("#### 💬 Conversation Sessions")
    
    # New session button
    if st.button("➕ New Conversation", use_container_width=True):
        st.session_state.session_id = f"sess-{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.rerun()

    # Session switcher
    sessions = db_list_chat_sessions(user_id="guest", limit=20)
    session_options = [s["session_id"] for s in sessions]
    if st.session_state.session_id not in session_options:
        session_options.insert(0, st.session_state.session_id)

    selected_sess = st.selectbox(
        "Switch Conversation",
        options=session_options,
        index=session_options.index(st.session_state.session_id),
    )
    if selected_sess != st.session_state.session_id:
        st.session_state.session_id = selected_sess
        st.session_state.messages = []
        existing = db_get_session_turns(user_id="guest", session_id=selected_sess)
        for t in existing:
            st.session_state.messages.append({"role": "user", "content": t["user_message"]})
            st.session_state.messages.append({
                "role": "assistant",
                "content": t["spoken_reply"],
                "tool_calls": json.loads(t["tool_calls"]) if isinstance(t.get("tool_calls"), str) else (t.get("tool_calls") or []),
            })
        st.rerun()

    if st.button("🗑️ Clear Current History", use_container_width=True):
        db_clear_chat_history(user_id="guest", session_id=st.session_state.session_id)
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("#### 💡 Quick Voice Prompts")
    prompt_samples = [
        "What is 18% of 5000 + 450 * 12?",
        "What time is it in New Delhi right now?",
        "Open YouTube and search for lofi music",
        "Open WhatsApp to message Krish saying hello",
        "Send an email to john@example.com about project update",
        "Calculate the first 10 Fibonacci numbers in Python",
        "Search latest cricket score",
    ]
    for p in prompt_samples:
        if st.button(p, key=f"sample_{p[:15]}", use_container_width=True):
            execute_turn(p)
            st.rerun()


# --------------------------------------------------------------------------- #
# Main Content Area: Header, Voice Mic, and Chat Stream
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="nexus-header">
        <div class="nexus-logo">🎙️</div>
        <div>
            <h1 class="nexus-title">Nexus AI Voice Assistant</h1>
            <p class="nexus-subtitle">Streamlit Cloud Deployment • Real-Time Voice, GPT-4o & Function Tools</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Voice Recording Input Widget (st.audio_input)
# --------------------------------------------------------------------------- #
st.markdown("##### 🎙️ Voice Input")
audio_input_data = st.audio_input("Record your voice command (click mic, speak, then click stop):")

if audio_input_data is not None:
    # Check if this audio has already been processed to prevent re-running on redraw
    audio_bytes = audio_input_data.read()
    audio_hash = hash(audio_bytes)
    if st.session_state.last_processed_audio != audio_hash:
        st.session_state.last_processed_audio = audio_hash
        with st.spinner("Transcribing your speech via Whisper..."):
            transcribed_text = transcribe_uploaded_audio(audio_bytes)
            if transcribed_text:
                st.info(f"🗣️ Heard: *\"{transcribed_text}\"*")
                execute_turn(transcribed_text)
                st.rerun()
            else:
                st.warning("Could not clearly detect speech in the audio recording. Please try speaking again.")

# --------------------------------------------------------------------------- #
# Chat Stream Feed
# --------------------------------------------------------------------------- #
st.markdown("---")

if not st.session_state.messages:
    st.markdown("""
    <div style="text-align: center; padding: 40px 20px; color: #64748b;">
        <div style="font-size: 40px; margin-bottom: 12px;">👋</div>
        <h3 style="color: #94a3b8; font-weight: 600;">How can I help you today?</h3>
        <p style="font-size: 14px;">Speak using the microphone above, type a command below, or choose a sample prompt from the sidebar!</p>
    </div>
    """, unsafe_allow_html=True)

for idx, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant", avatar="🤖"):
            st.write(msg["content"])

            # Render Audio Player if audio bytes present
            if msg.get("audio_bytes"):
                st.audio(msg["audio_bytes"], format="audio/mp3", autoplay=(idx == len(st.session_state.messages) - 1))

            # Render executed tools
            tools = msg.get("tool_calls", [])
            if tools:
                for tc in tools:
                    tool_name = tc.get("tool", "")
                    tool_args = tc.get("args", {})
                    tool_res = tc.get("result", {})

                    if tool_name == "open_app" and tool_res.get("url"):
                        target_label = tool_res.get("target", "Application")
                        target_url = tool_res.get("url")
                        st.markdown(
                            f"""
                            <div class="tool-badge tool-badge-success">
                                🚀 Opened {target_label}: <a href="{target_url}" target="_blank" style="color: #38bdf8; text-decoration: underline; font-weight: bold;">Launch {target_label} in New Tab ↗</a>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    elif tool_name == "send_whatsapp_message" and tool_res.get("url"):
                        contact = tool_res.get("contact", "Contact")
                        wa_url = tool_res.get("url")
                        st.markdown(
                            f"""
                            <div class="tool-badge tool-badge-success">
                                💬 WhatsApp Chat Ready: <a href="{wa_url}" target="_blank" style="color: #22c55e; text-decoration: underline; font-weight: bold;">Open WhatsApp Web Chat with {contact} ↗</a>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    elif tool_name == "calculator" and tool_res.get("success"):
                        st.markdown(
                            f"""
                            <div class="tool-badge">
                                🧮 Math Calculated: <code>{tool_args.get('expression')}</code> = <strong>{tool_res.get('formatted', tool_res.get('result'))}</strong>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    elif tool_name == "send_email" and tool_res.get("success"):
                        to_email = tool_res.get("to", "recipient")
                        subj = tool_res.get("subject", "No Subject")
                        sender = tool_res.get("from", "Gmail")
                        st.markdown(
                            f"""
                            <div class="tool-badge tool-badge-success">
                                ✉️ Email Sent to {to_email} (From: {sender}) | Subject: "{subj}"
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                    with st.expander(f"🛠️ View Tool Details: `{tool_name}`", expanded=False):
                        st.json({"tool": tool_name, "arguments": tool_args, "result": tool_res})

            # Check if this message requires safety confirmation
            if msg.get("requires_confirmation") and idx == len(st.session_state.messages) - 1:
                st.warning(f"⚠️ {msg.get('confirmation_question', 'Confirmation required. Would you like to proceed?')}")
                col_c1, col_c2, _ = st.columns([1, 1, 3])
                with col_c1:
                    if st.button("✅ Yes, Proceed", key=f"confirm_yes_{idx}"):
                        execute_turn("yes")
                        st.rerun()
                with col_c2:
                    if st.button("❌ No, Cancel", key=f"confirm_no_{idx}"):
                        execute_turn("no")
                        st.rerun()

# --------------------------------------------------------------------------- #
# Chat Text Input
# --------------------------------------------------------------------------- #
user_chat_input = st.chat_input("Type a message or command (e.g. 'what is 25 * 40', 'open youtube', 'what time is it')...")
if user_chat_input:
    execute_turn(user_chat_input)
    st.rerun()
