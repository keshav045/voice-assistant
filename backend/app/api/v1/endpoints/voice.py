"""Voice session REST and WebSocket streaming endpoints."""

import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import AsyncSessionLocal, get_db
from app.models.voice import VoiceSession
from app.services.voice.base import AudioData, AudioFormat
from app.services.voice.modular_pipeline import ModularVoicePipeline

router = APIRouter()
logger = logging.getLogger("nexus.api.voice")


# --- Request/Response Schemas ---
class VoiceSessionCreate(BaseModel):
    conversation_id: Optional[uuid.UUID] = None
    provider_mode: str = "modular"  # "modular" or "realtime"


class VoiceSessionResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    provider_mode: str
    ws_url: str
    started_at: datetime
    metrics: Dict[str, Any]


# --- REST Endpoints ---
@router.post("/session", response_model=VoiceSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_session(
    session_in: Optional[VoiceSessionCreate] = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new voice session and return the streaming WebSocket URL."""
    provider_mode = session_in.provider_mode if session_in else "modular"
    conversation_id = session_in.conversation_id if session_in else None

    voice_session = VoiceSession(
        status="active",
        provider_mode=provider_mode,
        conversation_id=conversation_id,
        metrics={"turns": [], "total_turns": 0},
    )
    db.add(voice_session)
    await db.commit()
    await db.refresh(voice_session)

    return VoiceSessionResponse(
        session_id=voice_session.id,
        status=voice_session.status,
        provider_mode=voice_session.provider_mode,
        ws_url=f"/ws/voice/{voice_session.id}",
        started_at=voice_session.started_at,
        metrics=voice_session.metrics or {},
    )


@router.get("/session/{session_id}", response_model=VoiceSessionResponse)
async def get_voice_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve details and metrics of an existing voice session."""
    result = await db.execute(select(VoiceSession).where(VoiceSession.id == session_id))
    voice_session = result.scalar_one_or_none()
    if not voice_session:
        raise HTTPException(status_code=404, detail="Voice session not found")

    return VoiceSessionResponse(
        session_id=voice_session.id,
        status=voice_session.status,
        provider_mode=voice_session.provider_mode,
        ws_url=f"/ws/voice/{voice_session.id}",
        started_at=voice_session.started_at,
        metrics=voice_session.metrics or {},
    )


@router.post("/session/{session_id}/end")
async def end_voice_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """End a voice session and record completion timestamp."""
    result = await db.execute(select(VoiceSession).where(VoiceSession.id == session_id))
    voice_session = result.scalar_one_or_none()
    if not voice_session:
        raise HTTPException(status_code=404, detail="Voice session not found")

    voice_session.status = "completed"
    voice_session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "completed", "session_id": str(session_id)}


# --- WebSocket Voice Streaming Endpoint ---
@router.websocket("/ws/{session_id}")
async def voice_websocket_channel(
    websocket: WebSocket,
    session_id: uuid.UUID,
):
    """Bidirectional streaming WebSocket channel for voice conversation."""
    await websocket.accept()
    logger.info(f"WebSocket voice client connected for session {session_id}")

    pipeline = ModularVoicePipeline()
    conversation_history: List[Dict[str, str]] = []
    is_interrupted = False

    # Send initial session greeting event
    await websocket.send_json({
        "type": "session_ready",
        "session_id": str(session_id),
        "message": "Nexus voice engine connected and ready for audio streaming.",
    })

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
            except Exception:
                await websocket.send_json({"type": "error", "message": "Invalid JSON format."})
                continue

            msg_type = msg.get("type")

            # 1. Keepalive ping/pong
            if msg_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            # 2. Interruption request
            if msg_type == "interrupt":
                is_interrupted = True
                await websocket.send_json({
                    "type": "interrupted",
                    "message": "Assistant speech interrupted by user.",
                })
                continue

            # 3. Audio Turn (User spoke and recorded audio chunk)
            if msg_type == "audio":
                is_interrupted = False
                base64_data = msg.get("data", "")
                audio_format = msg.get("format", "webm")

                if not base64_data:
                    await websocket.send_json({"type": "error", "message": "Empty audio data."})
                    continue

                try:
                    audio_bytes = base64.b64decode(base64_data)
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Base64 decode error: {e}"})
                    continue

                fmt = AudioFormat.WEBM if audio_format == "webm" else AudioFormat.WAV
                audio_payload = AudioData(data=audio_bytes, format=fmt)

                # Process turn through modular pipeline
                try:
                    turn_result = await pipeline.process_audio_turn(
                        audio=audio_payload,
                        conversation_history=conversation_history,
                    )

                    if is_interrupted:
                        logger.info("Turn output skipped due to user interruption")
                        continue

                    # Send User Transcription event
                    await websocket.send_json({
                        "type": "transcript_user",
                        "text": turn_result.user_transcript,
                    })

                    # Send Assistant Response event
                    await websocket.send_json({
                        "type": "transcript_assistant",
                        "text": turn_result.assistant_text,
                    })

                    # Send Assistant Audio event
                    audio_base64 = base64.b64encode(turn_result.audio_bytes).decode("utf-8")
                    await websocket.send_json({
                        "type": "audio",
                        "data": audio_base64,
                        "format": turn_result.audio_format.value,
                    })

                    # Send Metrics & Turn Completion event
                    turn_metrics = {
                        "stt_latency_ms": turn_result.metrics.stt_latency_ms,
                        "llm_latency_ms": turn_result.metrics.llm_latency_ms,
                        "tts_latency_ms": turn_result.metrics.tts_latency_ms,
                        "total_latency_ms": turn_result.metrics.total_latency_ms,
                    }
                    await websocket.send_json({
                        "type": "turn_complete",
                        "metrics": turn_metrics,
                    })

                    # Update history
                    conversation_history.append({"role": "user", "content": turn_result.user_transcript})
                    conversation_history.append({"role": "assistant", "content": turn_result.assistant_text})

                    # Persist turn metric to DB
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(VoiceSession).where(VoiceSession.id == session_id)
                        )
                        vs = result.scalar_one_or_none()
                        if vs:
                            vs.total_turns += 1
                            m = vs.metrics or {}
                            turns_list = m.get("turns", [])
                            turns_list.append(turn_metrics)
                            m["turns"] = turns_list
                            m["total_turns"] = vs.total_turns
                            vs.metrics = dict(m)
                            await session.commit()

                except Exception as e:
                    logger.error(f"Voice processing error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Processing error: {str(e)}",
                    })

            # 4. Text Turn (User typed into voice chat)
            elif msg_type == "text":
                is_interrupted = False
                user_text = msg.get("text", "")
                if not user_text:
                    continue

                try:
                    turn_result = await pipeline.process_text_turn(
                        text=user_text,
                        conversation_history=conversation_history,
                    )

                    await websocket.send_json({
                        "type": "transcript_user",
                        "text": user_text,
                    })
                    await websocket.send_json({
                        "type": "transcript_assistant",
                        "text": turn_result.assistant_text,
                    })

                    audio_base64 = base64.b64encode(turn_result.audio_bytes).decode("utf-8")
                    await websocket.send_json({
                        "type": "audio",
                        "data": audio_base64,
                        "format": turn_result.audio_format.value,
                    })

                    await websocket.send_json({
                        "type": "turn_complete",
                        "metrics": {
                            "llm_latency_ms": turn_result.metrics.llm_latency_ms,
                            "tts_latency_ms": turn_result.metrics.tts_latency_ms,
                            "total_latency_ms": turn_result.metrics.total_latency_ms,
                        },
                    })

                    conversation_history.append({"role": "user", "content": user_text})
                    conversation_history.append({"role": "assistant", "content": turn_result.assistant_text})

                except Exception as e:
                    logger.error(f"Voice text turn error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Text turn error: {str(e)}",
                    })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket unexpected error: {e}")
