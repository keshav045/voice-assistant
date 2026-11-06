"""Unit and integration tests for LiveKit WebRTC endpoints and agent worker."""

import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from agent.main import app


def test_livekit_status_unconfigured():
    client = TestClient(app)
    with patch.dict(os.environ, {"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}):
        res = client.get("/api/livekit/status")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["url"] is None


def test_livekit_token_unconfigured():
    client = TestClient(app)
    with patch.dict(os.environ, {"LIVEKIT_URL": "", "LIVEKIT_API_KEY": "", "LIVEKIT_API_SECRET": ""}):
        res = client.get("/api/livekit/token")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "not configured" in data["error"].lower()


def test_livekit_status_and_token_configured():
    client = TestClient(app)
    with patch.dict(os.environ, {
        "LIVEKIT_URL": "wss://nexus-demo.livekit.cloud",
        "LIVEKIT_API_KEY": "API12345678901234567890",
        "LIVEKIT_API_SECRET": "secretsecretsecret12345678901234567890"
    }):
        # Status
        res_s = client.get("/api/livekit/status")
        assert res_s.status_code == 200
        assert res_s.json()["configured"] is True
        assert res_s.json()["url"] == "wss://nexus-demo.livekit.cloud"

        # Token
        res_t = client.get("/api/livekit/token?room=custom-room&name=Tester")
        assert res_t.status_code == 200
        data = res_t.json()
        assert data["success"] is True
        assert data["room"] == "custom-room"
        assert data["url"] == "wss://nexus-demo.livekit.cloud"
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 50


def test_livekit_tools_instantiation():
    """Verify that all livekit tools import and wrap properly."""
    from agent.livekit_worker import LIVEKIT_TOOLS
    assert len(LIVEKIT_TOOLS) >= 7
    tool_names = [t.info.name for t in LIVEKIT_TOOLS]
    assert "web_search" in tool_names
    assert "calculator" in tool_names
    assert "send_email" in tool_names
    assert "open_app" in tool_names
    assert "send_whatsapp_message" in tool_names
