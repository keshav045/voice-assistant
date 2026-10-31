"""Integration tests for Phase 7: Windows Desktop Companion & Policy Guardrails."""

import json
import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from app.main import app
from app.agents.policy import PolicyEngine
from app.services.desktop_manager import desktop_manager, ALLOWED_APPLICATIONS


@pytest.mark.asyncio
async def test_desktop_status_endpoint():
    """Verify desktop status returns companion telemetry and allowlisted applications."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/desktop/status")
        assert res.status_code == 200
        data = res.json()
        assert "is_connected" in data
        assert "allowed_applications" in data
        assert "notepad" in data["allowed_applications"]
        assert "calculator" in data["allowed_applications"]


@pytest.mark.asyncio
async def test_desktop_safe_read_commands():
    """Verify safe read commands execute autonomously without approval."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Active window query
        win_res = await client.post(
            "/api/v1/desktop/command",
            json={"action": "get_active_window"},
        )
        assert win_res.status_code == 200
        win_data = win_res.json()
        assert win_data["success"] is True

        # Safe file search
        search_res = await client.post(
            "/api/v1/desktop/command",
            json={"action": "search_files", "params": {"query": "plan"}},
        )
        assert search_res.status_code == 200
        search_data = search_res.json()
        assert search_data["success"] is True


@pytest.mark.asyncio
async def test_desktop_approval_gated_action():
    """Verify launching applications requires approval, and proceeds when approved."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Propose without approval -> gated
        gated_res = await client.post(
            "/api/v1/desktop/command",
            json={
                "action": "open_application",
                "params": {"app_name": "calculator"},
                "approval_granted": False,
            },
        )
        assert gated_res.status_code == 200
        gated_data = gated_res.json()
        assert gated_data.get("approval_required") is True
        assert "requires explicit human approval" in gated_data.get("message", "")

        # 2. Execute with approval granted -> allowed
        exec_res = await client.post(
            "/api/v1/desktop/command",
            json={
                "action": "open_application",
                "params": {"app_name": "calculator"},
                "approval_granted": True,
            },
        )
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["success"] is True
        assert "calculator" in exec_data["message"]


@pytest.mark.asyncio
async def test_disallowed_application_blocked():
    """Verify unapproved applications are rejected even if approval is requested."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/desktop/command",
            json={
                "action": "open_application",
                "params": {"app_name": "unauthorized_malware_tool"},
                "approval_granted": True,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "not in the approved desktop allowlist" in data["error"]


def test_companion_websocket_handshake():
    """Verify Windows companion WebSocket handshake and heartbeat exchange."""
    client = TestClient(app)
    with client.websocket_connect("/ws/desktop/companion") as websocket:
        # Send handshake
        handshake = {
            "type": "companion_handshake",
            "hostname": "TEST-WIN11-WORKSTATION",
            "os": "Windows 11 Pro 23H2",
            "capabilities": ["app_launcher", "active_window", "safe_file_search"],
        }
        websocket.send_text(json.dumps(handshake))

        # Receive ack
        ack_raw = websocket.receive_text()
        ack = json.loads(ack_raw)
        assert ack["type"] == "handshake_ack"
        assert ack["status"] == "ready"

        # Check status shows connected
        assert desktop_manager.is_connected is True
        assert desktop_manager.get_status()["hostname"] == "TEST-WIN11-WORKSTATION"

        # Send heartbeat
        websocket.send_text(json.dumps({"type": "heartbeat"}))
        hb_ack_raw = websocket.receive_text()
        hb_ack = json.loads(hb_ack_raw)
        assert hb_ack["type"] == "heartbeat_ack"
