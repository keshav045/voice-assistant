"""Unit and integration tests for LiveKit WebRTC endpoints and agent worker."""

import os
import pytest
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


@pytest.mark.asyncio
async def test_local_edge_tts_stream_adapter_real_streaming():
    """Verify that LocalEdgeTTS properly streams audio through LiveKit StreamAdapter without raising NotImplementedError."""
    from livekit.agents import tts
    from agent.local_voice import LocalEdgeTTS

    edge = LocalEdgeTTS()
    adapter = tts.StreamAdapter(tts=edge)
    stream = adapter.stream()
    assert stream is not None
    stream.push_text("Unit test audio synthesis.")
    stream.flush()
    stream.end_input()
    frames = []
    async for f in stream:
        frames.append(f)
    assert len(frames) > 0


@pytest.mark.asyncio
async def test_livekit_tool_pleasantry_guard():
    """Verify that conversational pleasantries do not trigger unconstrained web searches in LiveKit."""
    from agent.livekit_worker import web_search

    res = await web_search("hello")
    assert "listening" in res.lower()

    res2 = await web_search("let me take a look")
    assert "listening" in res2.lower()


@pytest.mark.asyncio
async def test_livekit_send_email_validation():
    """Verify that send_email strictly checks recipient address format before dispatching."""
    from agent.livekit_worker import send_email

    res = await send_email("invalid-address", "test description")
    assert "valid" in res.lower()

