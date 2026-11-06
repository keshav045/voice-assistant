"""Nexus AI — LiveKit WebRTC Voice Agent Launcher.

Usage:
  Development mode (hot reload):
    python run_livekit.py dev

  Production / download models:
    python run_livekit.py download-files
    python run_livekit.py start
"""

from __future__ import annotations

import os
import sys

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from livekit.agents import cli
from agent.livekit_worker import server_options

if __name__ == "__main__":
    cli.run_app(server_options)
