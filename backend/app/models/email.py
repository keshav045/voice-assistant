"""Email Drafts and Gmail Integration SQLAlchemy models."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base
from app.models.user import GUID


class EmailDraft(Base):
    """Email draft model for prepared messages requiring approval before sending."""

    __tablename__ = "email_drafts"

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
    recipient: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),  # "draft", "pending_approval", "sent", "discarded"
        default="draft",
        nullable=False,
        index=True,
    )
    gmail_draft_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    __table_args__ = (
        Index("ix_email_drafts_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<EmailDraft(id={self.id}, recipient='{self.recipient}', subject='{self.subject}', status='{self.status}')>"
