"""Integration and unit tests for Phase 2 Voice Engine."""

import base64
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database.session import init_db
from app.services.voice.base import AudioData, AudioFormat
from app.services.voice.modular_pipeline import ModularVoicePipeline


@pytest.fixture(autouse=True)
async def setup_database():
    """Ensure database tables are initialized before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_create_and_get_voice_session():
    """Test creating and retrieving voice sessions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create session
        res = await client.post(
            "/api/v1/voice/session",
            json={"provider_mode": "modular"},
        )
        assert res.status_code == 201
        data = res.json()
        assert "session_id" in data
        assert data["status"] == "active"
        assert data["provider_mode"] == "modular"
        assert f"/ws/voice/{data['session_id']}" in data["ws_url"]

        session_id = data["session_id"]

        # 2. Get session
        get_res = await client.get(f"/api/v1/voice/session/{session_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["session_id"] == session_id

        # 3. End session
        end_res = await client.post(f"/api/v1/voice/session/{session_id}/end")
        assert end_res.status_code == 200
        assert end_res.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_modular_voice_pipeline_text_turn():
    """Test modular voice pipeline processing text to speech."""
    pipeline = ModularVoicePipeline()
    result = await pipeline.process_text_turn(
        text="Hello Nexus, schedule a meeting.",
        conversation_history=[],
    )
    assert result.user_transcript == "Hello Nexus, schedule a meeting."
    assert len(result.assistant_text) > 0
    assert len(result.audio_bytes) > 0
    assert result.metrics.total_latency_ms >= 0


@pytest.mark.asyncio
async def test_modular_voice_pipeline_audio_turn():
    """Test modular voice pipeline processing audio data."""
    pipeline = ModularVoicePipeline()
    dummy_audio = AudioData(data=b"DUMMY_AUDIO_PAYLOAD", format=AudioFormat.WEBM)

    result = await pipeline.process_audio_turn(
        audio=dummy_audio,
        conversation_history=[],
    )
    assert len(result.user_transcript) > 0
    assert len(result.assistant_text) > 0
    assert len(result.audio_bytes) > 0
    assert result.metrics.stt_latency_ms >= 0
    assert result.metrics.llm_latency_ms >= 0
    assert result.metrics.tts_latency_ms >= 0
    assert result.metrics.total_latency_ms >= 0


def test_voice_websocket_full_interaction():
    """Test WebSocket connection, keepalive, voice text turn, and interruption."""
    client = TestClient(app)

    # 1. Create a session via REST first
    res = client.post("/api/v1/voice/session", json={"provider_mode": "modular"})
    assert res.status_code == 201
    session_id = res.json()["session_id"]

    # 2. Connect to WebSocket
    with client.websocket_connect(f"/ws/voice/{session_id}") as ws:
        # Verify initial greeting
        ready_msg = ws.receive_json()
        assert ready_msg["type"] == "session_ready"
        assert ready_msg["session_id"] == session_id

        # Keepalive ping
        ws.send_json({"type": "ping"})
        pong_msg = ws.receive_json()
        assert pong_msg["type"] == "pong"
        assert "timestamp" in pong_msg

        # Send text turn
        ws.send_json({"type": "text", "text": "Nexus, create a priority task for tomorrow."})

        # Expect transcript_user
        msg1 = ws.receive_json()
        assert msg1["type"] == "transcript_user"
        assert "create a priority task" in msg1["text"]

        # Expect transcript_assistant
        msg2 = ws.receive_json()
        assert msg2["type"] == "transcript_assistant"
        assert len(msg2["text"]) > 0

        # Expect audio payload
        msg3 = ws.receive_json()
        assert msg3["type"] == "audio"
        assert len(msg3["data"]) > 0

        # Expect turn_complete with metrics
        msg4 = ws.receive_json()
        assert msg4["type"] == "turn_complete"
        assert "metrics" in msg4
        assert "total_latency_ms" in msg4["metrics"]

        # Interruption test
        ws.send_json({"type": "interrupt"})
        int_msg = ws.receive_json()
        assert int_msg["type"] == "interrupted"
