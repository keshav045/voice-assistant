"""Semantic Memory and Vector Storage SQLAlchemy models."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base
from app.models.user import GUID


class MemoryItem(Base):
    """Semantic memory item storing learned user facts, preferences, and embeddings."""

    __tablename__ = "memory_items"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(50),  # "preference", "fact", "goal", "interaction", "system"
        default="fact",
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    # Stored as serialized 1536-dimensional float vector
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        JSON,
        nullable=True,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),  # "conversation", "manual", "voice_turn"
        default="conversation",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="memories", lazy="selectin")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory item to dict."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "category": self.category,
            "content": self.content,
            "confidence": self.confidence,
            "source": self.source,
            "has_embedding": self.embedding is not None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
