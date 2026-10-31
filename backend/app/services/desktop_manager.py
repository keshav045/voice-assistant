"""Desktop Companion Connection Manager and WebSocket Hub."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import WebSocket

logger = logging.getLogger("nexus.desktop.manager")

# Strict application and command allowlists for Windows 11 companion
ALLOWED_APPLICATIONS: Dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "taskmgr": "taskmgr.exe",
    "terminal": "wt.exe",
    "browser": "msedge.exe",
    "code": "code.cmd",
}

SAFE_FILE_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".py", ".ts", ".tsx", ".html", ".css", ".pdf", ".png", ".jpg"}


class DesktopCompanionManager:
    """Singleton manager maintaining active WebSocket connection to local Windows desktop companion."""

    def __init__(self):
        self._active_socket: Optional[WebSocket] = None
        self._companion_info: Dict[str, Any] = {
            "status": "disconnected",
            "hostname": None,
            "os": None,
            "connected_at": None,
            "last_heartbeat": None,
            "capabilities": ["app_launcher", "active_window", "safe_file_search", "system_metrics"],
        }
        self._pending_commands: Dict[str, asyncio.Future] = {}

    @property
    def is_connected(self) -> bool:
        return self._active_socket is not None and self._companion_info["status"] == "connected"

    def get_status(self) -> Dict[str, Any]:
        """Return live companion connection telemetry."""
        return {
            "is_connected": self.is_connected,
            **self._companion_info,
            "allowed_applications": list(ALLOWED_APPLICATIONS.keys()),
        }

    async def register_connection(self, websocket: WebSocket, handshake_data: Dict[str, Any]):
        """Register active companion WebSocket after successful handshake."""
        self._active_socket = websocket
        self._companion_info.update({
            "status": "connected",
            "hostname": handshake_data.get("hostname", "WINDOWS-HOST"),
            "os": handshake_data.get("os", "Windows 11"),
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "capabilities": handshake_data.get("capabilities", self._companion_info["capabilities"]),
        })
        logger.info(f"Desktop companion registered from {self._companion_info['hostname']}")

    def update_heartbeat(self):
        """Update last known heartbeat timestamp."""
        self._companion_info["last_heartbeat"] = datetime.now(timezone.utc).isoformat()

    def disconnect(self):
        """Clean up companion session on disconnection."""
        self._active_socket = None
        self._companion_info["status"] = "disconnected"
        # Cancel any pending command futures
        for cmd_id, fut in list(self._pending_commands.items()):
            if not fut.done():
                fut.set_exception(ConnectionError("Desktop companion disconnected"))
        self._pending_commands.clear()
        logger.info("Desktop companion disconnected.")

    async def dispatch_command(
        self,
        command_type: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Dispatch a validated command to the connected desktop companion and wait for result."""
        params = params or {}
        cmd_id = f"cmd-{uuid.uuid4().hex[:8]}"

        # Validate against strict allowlists
        if command_type == "open_application":
            app_key = params.get("app_name", "").lower()
            if app_key not in ALLOWED_APPLICATIONS:
                return {
                    "success": False,
                    "error": f"Application '{app_key}' is not in the approved desktop allowlist.",
                    "allowed_apps": list(ALLOWED_APPLICATIONS.keys()),
                }

        # Offline / Mock simulation fallback if companion is not physically attached yet
        if not self._active_socket:
            logger.info(f"Companion offline: simulating safe execution for '{command_type}'")
            return self._simulate_safe_command(command_type, params)

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_commands[cmd_id] = future

        try:
            payload = {
                "id": cmd_id,
                "command": command_type,
                "params": params,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self._active_socket.send_text(json.dumps(payload))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Companion timed out after {timeout}s executing '{command_type}'.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._pending_commands.pop(cmd_id, None)

    def handle_command_response(self, response_data: Dict[str, Any]):
        """Receive command execution result from companion and resolve awaiting future."""
        cmd_id = response_data.get("id")
        if cmd_id and cmd_id in self._pending_commands:
            fut = self._pending_commands[cmd_id]
            if not fut.done():
                fut.set_result(response_data)

    def _simulate_safe_command(self, command_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate safe execution when companion is running locally or in development."""
        if command_type == "open_application":
            app = params.get("app_name", "notepad")
            return {
                "success": True,
                "message": f"Successfully launched allowlisted application '{app}' (executable: {ALLOWED_APPLICATIONS.get(app)}).",
                "simulated": True,
            }
        elif command_type == "get_active_window":
            return {
                "success": True,
                "title": "Nexus Agentic AI Dashboard - Google Chrome",
                "process": "chrome.exe",
                "simulated": True,
            }
        elif command_type == "get_system_metrics":
            return {
                "success": True,
                "cpu_usage_pct": 14.2,
                "memory_used_gb": 8.6,
                "memory_total_gb": 16.0,
                "simulated": True,
            }
        elif command_type == "search_files":
            query = params.get("query", "project")
            return {
                "success": True,
                "query": query,
                "matches": [
                    {"name": "Nexus_Implementation_Plan.pdf", "path": "c:\\Users\\kesha\\OneDrive\\Desktop\\voice assistant\\Nexus_Implementation_Plan.pdf", "size_kb": 240},
                    {"name": "requirements.txt", "path": "c:\\Users\\kesha\\OneDrive\\Desktop\\voice assistant\\backend\\requirements.txt", "size_kb": 2},
                ],
                "simulated": True,
            }
        return {
            "success": True,
            "message": f"Command '{command_type}' executed successfully.",
            "simulated": True,
        }


# Global singleton manager instance
desktop_manager = DesktopCompanionManager()
