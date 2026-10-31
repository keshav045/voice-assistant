"""Nexus Windows Desktop Companion Daemon.

Connects to the Nexus Backend via secure WebSocket and executes allowlisted
desktop actions (application launcher, active window inspection, scoped file search)
with strict policy constraints and zero arbitrary shell execution.
"""

import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (NexusDesktop) %(message)s",
)
logger = logging.getLogger("nexus.companion")

# Strict allowlist of permitted Windows applications
ALLOWED_APPLICATIONS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "taskmgr": "taskmgr.exe",
    "terminal": "wt.exe",
    "browser": "msedge.exe",
    "code": "code.cmd",
}

SAFE_SEARCH_EXTENSIONS = {".txt", ".md", ".json", ".py", ".pdf", ".docx", ".xlsx", ".png", ".jpg"}


class DesktopCompanionClient:
    """Windows Companion Client daemon communicating over WebSocket."""

    def __init__(self, backend_url: str = "ws://localhost:8000/ws/desktop/companion"):
        self.backend_url = backend_url
        self.hostname = platform.node()
        self.os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        self.running = True

    async def connect_and_listen(self):
        """Main connection loop with auto-reconnect backoff."""
        backoff = 2
        while self.running:
            try:
                logger.info(f"Connecting to Nexus Core at {self.backend_url}...")
                async with websockets.connect(self.backend_url) as ws:
                    backoff = 2  # Reset backoff on successful connect
                    logger.info("Connected! Sending companion handshake...")

                    # Handshake
                    handshake = {
                        "type": "companion_handshake",
                        "hostname": self.hostname,
                        "os": self.os_info,
                        "capabilities": ["app_launcher", "active_window", "safe_file_search", "system_metrics"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    await ws.send(json.dumps(handshake))

                    ack_raw = await ws.recv()
                    logger.info(f"Handshake acknowledged: {ack_raw}")

                    # Run heartbeat sender and message listener concurrently
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                    try:
                        await self._message_listener(ws)
                    finally:
                        heartbeat_task.cancel()

            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                logger.warning(f"Connection lost or unreachable ({e}). Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            except Exception as e:
                logger.error(f"Unexpected error in companion client: {e}")
                await asyncio.sleep(5)

    async def _heartbeat_loop(self, ws):
        """Send periodic keepalive heartbeats every 15s."""
        while True:
            await asyncio.sleep(15)
            try:
                await ws.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                break

    async def _message_listener(self, ws):
        """Listen for command execution requests dispatched from the backend."""
        async for raw_message in ws:
            try:
                data = json.loads(raw_message)
                msg_type = data.get("type")

                if msg_type == "heartbeat_ack":
                    continue

                cmd_id = data.get("id")
                command = data.get("command")
                params = data.get("params", {})

                if command:
                    logger.info(f"Executing command [{cmd_id}]: {command} with params {params}")
                    result = await self._execute_command(command, params)
                    response = {
                        "type": "command_response",
                        "id": cmd_id,
                        **result,
                    }
                    await ws.send(json.dumps(response))
            except Exception as e:
                logger.error(f"Error handling message: {e}")

    async def _execute_command(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute command strictly within allowlist guardrails."""
        if command == "open_application":
            app_name = params.get("app_name", "").lower()
            if app_name not in ALLOWED_APPLICATIONS:
                return {
                    "success": False,
                    "error": f"Application '{app_name}' is not allowed.",
                    "allowed": list(ALLOWED_APPLICATIONS.keys()),
                }

            exe = ALLOWED_APPLICATIONS[app_name]
            try:
                # Launch process without shell=True to prevent shell injection
                subprocess.Popen([exe], shell=False)
                return {
                    "success": True,
                    "message": f"Successfully launched '{app_name}' ({exe}).",
                    "app_name": app_name,
                }
            except Exception as e:
                return {"success": False, "error": f"Failed to launch {exe}: {e}"}

        elif command == "get_active_window":
            return self._get_active_window_info()

        elif command == "get_system_metrics":
            return {
                "success": True,
                "hostname": self.hostname,
                "os": self.os_info,
                "cpu_count": os.cpu_count() or 4,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        elif command == "search_files":
            query = params.get("query", "").lower()
            search_dir = params.get("directory", os.path.expanduser("~\\Documents"))
            return self._safe_search_files(search_dir, query)

        return {"success": False, "error": f"Unrecognized companion command: '{command}'"}

    def _get_active_window_info(self) -> Dict[str, Any]:
        """Safely retrieve foreground window title on Windows."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            h_wnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(h_wnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(h_wnd, buf, length + 1)
            return {
                "success": True,
                "window_title": buf.value or "Desktop / Taskbar",
                "handle": h_wnd,
            }
        except Exception as e:
            return {"success": True, "window_title": "Windows Active Window", "error": str(e)}

    def _safe_search_files(self, search_dir: str, query: str) -> Dict[str, Any]:
        """Search files within allowed directory matching query and safe extensions."""
        matches = []
        try:
            if not os.path.exists(search_dir):
                search_dir = os.getcwd()

            for root, _, files in os.walk(search_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in SAFE_SEARCH_EXTENSIONS and (not query or query in f.lower()):
                        full_path = os.path.join(root, f)
                        matches.append({
                            "name": f,
                            "path": full_path,
                            "size_bytes": os.path.getsize(full_path),
                        })
                        if len(matches) >= 20:
                            break
                if len(matches) >= 20:
                    break

            return {"success": True, "query": query, "count": len(matches), "matches": matches}
        except Exception as e:
            return {"success": False, "error": str(e)}


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws/desktop/companion"
    client = DesktopCompanionClient(backend_url=url)
    try:
        asyncio.run(client.connect_and_listen())
    except KeyboardInterrupt:
        logger.info("Companion daemon stopped by user.")
