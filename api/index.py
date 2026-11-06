"""Vercel Serverless Function entry point for Nexus AI Voice Assistant."""
from __future__ import annotations

import os
import sys

# Ensure the project root directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Mark environment as serverless
os.environ.setdefault("VERCEL", "1")

# Import the configured FastAPI application
from agent.main import app  # noqa: E402

# Also export ASGI/WSGI handler for maximum serverless compatibility
try:
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except ImportError:
    handler = app

