"""Windows Desktop Companion REST and WebSocket API endpoints."""

import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from app.agents.desktop_agent import DesktopAgent
from app.services.desktop_manager import desktop_manager

logger = logging.getLogger("nexus.desktop.endpoints")
router = APIRouter()


class DesktopCommandRequest(BaseModel):
    action: str  # e.g., "open_application", "get_active_window", "get_system_metrics", "search_files"
    params: Optional[Dict[str, Any]] = None
    approval_granted: bool = False


@router.get("/status")
async def get_desktop_status() -> Dict[str, Any]:
    """Get status, connection details, and approved application allowlists of Desktop Companion."""
    return DesktopAgent.get_companion_status()


@router.post("/command")
async def execute_desktop_command(request: DesktopCommandRequest) -> Dict[str, Any]:
    """Execute a desktop command subject to allowlists and approval gates."""
    return await DesktopAgent.execute_desktop_action(
        action_name=request.action,
        params=request.params,
        approval_granted=request.approval_granted,
    )


# WebSocket endpoint for Windows Companion
@router.websocket("/ws/companion")
async def companion_websocket_endpoint(websocket: WebSocket):
    """WebSocket connection dedicated to the local Windows Desktop Companion daemon."""
    await websocket.accept()
    logger.info("Desktop companion connected via WebSocket.")

    try:
        # Await initial handshake payload
        handshake_raw = await websocket.receive_text()
        handshake_data = json.loads(handshake_raw)

        if handshake_data.get("type") != "companion_handshake":
            await websocket.send_text(json.dumps({"error": "Invalid handshake. Expected type 'companion_handshake'"}))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await desktop_manager.register_connection(websocket, handshake_data)
        await websocket.send_text(
            json.dumps({
                "type": "handshake_ack",
                "message": "Connected to Nexus Agentic Core",
                "status": "ready",
            })
        )

        while True:
            raw_msg = await websocket.receive_text()
            data = json.loads(raw_msg)
            msg_type = data.get("type")

            if msg_type == "heartbeat":
                desktop_manager.update_heartbeat()
                await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))
            elif msg_type == "command_response":
                desktop_manager.handle_command_response(data)
            else:
                logger.debug(f"Received companion message: {msg_type}")

    except WebSocketDisconnect:
        logger.info("Companion WebSocket disconnected.")
        desktop_manager.disconnect()
    except Exception as e:
        logger.error(f"Error in companion WebSocket: {e}")
        desktop_manager.disconnect()
