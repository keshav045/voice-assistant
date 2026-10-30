"""Voice session and audit logging models."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base
from app.models.user import GUID


class VoiceSession(Base):
    """Voice session record tracking conversation metrics and provider mode."""

    __tablename__ = "voice_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),  # "active", "completed", "error"
        default="active",
        nullable=False,
    )
    provider_mode: Mapped[str] = mapped_column(
        String(30),  # "modular" (STT->LLM->TTS) or "realtime" (OpenAI Realtime API)
        default="modular",
        nullable=False,
    )
    total_turns: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_voice_sessions_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<VoiceSession(id={self.id}, status='{self.status}', mode='{self.provider_mode}')>"

