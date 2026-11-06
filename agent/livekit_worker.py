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

@llm.function_tool
def web_search(query: str) -> str:
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
def calculator(expression: str) -> str:
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
def run_python_code(code: str) -> str:
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
def get_current_time(timezone: str = "Asia/Kolkata") -> str:
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
def open_app(name: str, query: str = "") -> str:
    """Open desktop applications (Calculator, Notepad, Explorer) or websites (YouTube, WhatsApp, LinkedIn, Spotify, GitHub, Gmail).

    Args:
        name: Name of the application or website (e.g., 'youtube', 'notepad', 'linkedin').
        query: Optional search topic or query (e.g., 'lofi music' for YouTube).
    """
    try:
        res = launcher.open_app(name=name, query=query)
        return res.get("spoken") or f"Opening {name}."
    except Exception as e:
        return f"Error opening application {name}: {e}"


@llm.function_tool
def send_whatsapp_message(contact_name: str, message: str = "") -> str:
    """Search for a contact in WhatsApp Web or Desktop, open their chat, and send a message.

    Args:
        contact_name: Name of the recipient contact (e.g., 'Krish', 'Alex', 'Mom').
        message: The message body to type and send.
    """
    try:
        res = whatsapp.send_whatsapp_message(contact_name=contact_name, message=message)
        return res.get("spoken") or f"Sent WhatsApp message to {contact_name}."
    except Exception as e:
        return f"Error sending WhatsApp message: {e}"


@llm.function_tool
def send_email(to: str, description: str, recipient_name: str = "") -> str:
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
    logger.info(f"Connecting to LiveKit room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Initialize Voice Pipeline Session
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=openai.STT(),
        llm=openai.LLM(model=os.environ.get("OPENAI_MODEL", "gpt-4o")),
        tts=openai.TTS(voice=os.environ.get("OPENAI_TTS_VOICE", "alloy")),
        allow_interruptions=True,
    )

    # Create Voice Agent with persona instructions and tools
    agent = Agent(
        instructions=SYSTEM_PROMPT,
        tools=LIVEKIT_TOOLS,
    )

    # Start audio pipeline on room
    session.start(agent, room=ctx.room)

    # Greet participant on join
    try:
        await session.say(
            "Hello! I am Nexus AI. I'm connected via LiveKit WebRTC and ready to assist you.",
            allow_interruptions=True,
        )
    except Exception as e:
        logger.warning(f"Initial greeting skipped: {e}")


server_options = WorkerOptions(entrypoint_fnc=entrypoint)
