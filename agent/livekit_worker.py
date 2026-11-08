"""Nexus AI — LiveKit WebRTC Voice Pipeline Worker.

Provides real-time, sub-500ms voice interactions over WebRTC using:
- LiveKit Agents framework
- Silero VAD (Voice Activity Detection)
- OpenAI STT (Whisper) & TTS (Alloy/Echo)
- OpenAI GPT-4o with integrated Nexus autonomous tools
"""

from __future__ import annotations

import json
import logging
import os
import sys

# Ensure root is in path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(override=True)

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, llm
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import openai, silero

from agent.prompts import SYSTEM_PROMPT
from agent.tools import (
    calc,
    coding,
    email,
    launcher,
    search,
    whatsapp,
)

logger = logging.getLogger("nexus.livekit_worker")


# --------------------------------------------------------------------------- #
# Tool Definitions for LiveKit Agents
# --------------------------------------------------------------------------- #

_active_room: Optional[Any] = None


async def _broadcast_client_action(action_type: str, data: dict):
    """Publish an automated action (e.g. open URL) to the web client via LiveKit data channel."""
    global _active_room
    if not _active_room or not getattr(_active_room, "local_participant", None):
        return
    import json
    try:
        payload = json.dumps({"type": action_type, **data}).encode("utf-8")
        await _active_room.local_participant.publish_data(payload, reliable=True)
    except Exception as e:
        logger.debug(f"Could not publish data action to room: {e}")


@llm.function_tool
async def web_search(query: str) -> str:
    """Search Google News and DuckDuckGo for live news, real-time facts, cricket scores, and current events.

    Args:
        query: The search query (e.g., 'latest tech news', 'IND vs NZ cricket score').
    """
    try:
        res = search.web_search(query=query)
        return res.get("spoken") or str(res)
    except Exception as e:
        return f"Error searching the web: {e}"


@llm.function_tool
async def calculator(expression: str) -> str:
    """Safely calculate mathematical equations, percentages, powers, or arithmetic expressions.

    Args:
        expression: The math expression to evaluate (e.g., '450 * 12 + 18% of 5000', 'sqrt(144)').
    """
    try:
        res = calc.calculate(expression=expression)
        return res.get("spoken") or str(res.get("result"))
    except Exception as e:
        return f"Error calculating: {e}"


@llm.function_tool
async def run_python_code(code: str) -> str:
    """Execute Python code in an isolated REPL to test algorithms, compute logic, or verify scripts.

    Args:
        code: The Python script or code snippet to run.
    """
    try:
        res = coding.run_python_code(code=code)
        return res.get("spoken") or (res.get("output") or "Code executed with no output.")
    except Exception as e:
        return f"Error executing Python code: {e}"


@llm.function_tool
async def get_current_time(timezone: str = "Asia/Kolkata") -> str:
    """Get the current time, date, day of week, and timezone.

    Args:
        timezone: The IANA timezone name (defaults to Asia/Kolkata).
    """
    try:
        from agent.main import get_current_time as gct
        res = gct(timezone=timezone)
        return res.get("spoken") or f"Current time is {res.get('time')} on {res.get('date')}."
    except Exception as e:
        return f"Error getting current time: {e}"


@llm.function_tool
async def open_app(name: str, query: str = "") -> str:
    """Open desktop applications (Calculator, Notepad, Explorer) or websites (YouTube, WhatsApp, LinkedIn, Spotify, GitHub, Gmail).

    Args:
        name: Name of the application or website (e.g., 'youtube', 'notepad', 'linkedin').
        query: Optional search topic or query (e.g., 'lofi music' for YouTube).
    """
    try:
        res = launcher.open_app(name=name, query=query)
        if res.get("url"):
            await _broadcast_client_action("OPEN_URL", {"url": res["url"], "target": res.get("target")})
        return res.get("spoken") or f"Opening {name}."
    except Exception as e:
        return f"Error opening application {name}: {e}"


@llm.function_tool
async def send_whatsapp_message(contact_name: str, message: str = "") -> str:
    """Search for a contact in WhatsApp Web or Desktop, open their chat, and send a message.

    Args:
        contact_name: Name of the recipient contact (e.g., 'Krish', 'Alex', 'Mom').
        message: The message body to type and send.
    """
    try:
        res = whatsapp.send_whatsapp_message(contact_name=contact_name, message=message)
        if res.get("url"):
            await _broadcast_client_action("OPEN_URL", {"url": res["url"], "target": "WhatsApp"})
        return res.get("spoken") or f"Sent WhatsApp message to {contact_name}."
    except Exception as e:
        return f"Error sending WhatsApp message: {e}"


@llm.function_tool
async def send_email(to: str, description: str, recipient_name: str = "") -> str:
    """Compose and send emails to a single recipient, multiple recipients, or bulk contacts from contacts.csv.

    Args:
        to: Recipient email address, comma-separated list, or 'contacts.csv'.
        description: Brief description of the email content to be professionally composed.
        recipient_name: Optional recipient name for greeting.
    """
    try:
        res = email.send_email(to=to, description=description, recipient_name=recipient_name)
        return res.get("spoken") or f"Email sent to {to}."
    except Exception as e:
        return f"Error delivering email: {e}"


LIVEKIT_TOOLS = [
    web_search,
    calculator,
    run_python_code,
    get_current_time,
    open_app,
    send_whatsapp_message,
    send_email,
]


# --------------------------------------------------------------------------- #
# LiveKit Voice Pipeline Entrypoint
# --------------------------------------------------------------------------- #

async def entrypoint(ctx: JobContext):
    """LiveKit agent worker entrypoint for WebRTC audio rooms."""
    global _active_room
    _active_room = ctx.room
    logger.info(f"Connecting to LiveKit room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the browser user to connect into the room
    logger.info("Waiting for user participant to connect...")
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant connected: {participant.identity} ({participant.name or 'User'})")

    # Initialize Voice Pipeline Session with optimized VAD sensitivity
    session = AgentSession(
        vad=silero.VAD.load(
            activation_threshold=0.35,
            min_speech_duration=0.05,
            min_silence_duration=0.55,
        ),
        stt=openai.STT(),
        llm=openai.LLM(model=os.environ.get("OPENAI_MODEL", "gpt-4o")),
        tts=openai.TTS(voice=os.environ.get("OPENAI_TTS_VOICE", "alloy")),
        allow_interruptions=True,
        min_endpointing_delay=0.4,
        max_endpointing_delay=3.0,
    )

    # Create Voice Agent with persona instructions and tools
    agent = Agent(
        instructions=SYSTEM_PROMPT,
        tools=LIVEKIT_TOOLS,
    )

    # Start audio pipeline on room (must be awaited so listening loop starts!)
    await session.start(agent, room=ctx.room)
    logger.info("AgentSession started and listening for voice input")

    # Greet participant on join
    try:
        await session.say(
            "Hello! I am Nexus AI. I'm connected via LiveKit WebRTC and listening. How can I help you?",
            allow_interruptions=True,
        )
    except Exception as e:
        logger.warning(f"Initial greeting skipped: {e}")


server_options = WorkerOptions(entrypoint_fnc=entrypoint)
