"""Root entrypoint to run the Nexus Voice Assistant.

Run directly with:
    python run_voice.py
    python run_voice.py --auto
    python run_voice.py --voice nova
"""

import sys
import os

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import asyncio
    from agent.cli import main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession finished.")

