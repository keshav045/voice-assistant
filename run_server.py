"""Production Server Launcher for Personal Voice Assistant.

Reads configuration from environment variables (.env):
- HOST (default: 0.0.0.0)
- PORT (default: 8000, dynamic for Render/Railway/Fly.io/Heroku/AWS)
- WORKERS (default: 1)
- RELOAD (default: false in production)
"""

import os
import sys
from dotenv import load_dotenv

# Ensure current workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "false").lower() in ("true", "1", "yes")
    workers = int(os.environ.get("WORKERS", "1")) if not reload else 1
    log_level = os.environ.get("LOG_LEVEL", "info").lower()

    print("=" * 65)
    print("   Starting Nexus AI Personal Voice Assistant (Production)")
    print(f"   Listening on: http://{host}:{port}")
    print(f"   API Docs:     http://{host}:{port}/docs")
    print(f"   Health Check: http://{host}:{port}/health")
    print(f"   Workers:      {workers} | Reload: {reload}")
    print("=" * 65)

    uvicorn.run(
        "agent.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
        log_level=log_level,
    )
