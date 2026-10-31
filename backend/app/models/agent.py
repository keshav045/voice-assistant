"""Agent operations, tool execution history, and approval gates models."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base
from app.models.user import GUID


class AgentRun(Base):
    """Execution run of an agent workflow."""

    __tablename__ = "agent_runs"

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
    request_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    user_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    normalized_intent: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    workflow_status: Mapped[str] = mapped_column(
        String(50),  # "running", "completed", "pending_approval", "failed"
        default="running",
        nullable=False,
    )
    error_details: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    final_response: Mapped[Optional[str]] = mapped_column(
        Text,
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

    # Relationships
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        "ToolExecution",
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )
    approvals: Mapped[list["ApprovalRequest"]] = relationship(
        "ApprovalRequest",
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agent_runs_status", "workflow_status"),
    )

    def __repr__(self) -> str:
        return f"<AgentRun(id={self.id}, status='{self.workflow_status}', intent='{self.normalized_intent}')>"


class ToolExecution(Base):
    """Audit log of individual tool execution within an agent run."""

    __tablename__ = "tool_executions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    tool_input: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    tool_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(30),  # "success", "failed", "pending_approval"
        nullable=False,
    )
    latency_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    agent_run: Mapped["AgentRun"] = relationship(
        "AgentRun",
        back_populates="tool_executions",
    )

    def __repr__(self) -> str:
        return f"<ToolExecution(id={self.id}, tool='{self.tool_name}', status='{self.status}')>"


class ApprovalRequest(Base):
    """Action requiring user confirmation before execution."""

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    action_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    tool_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(30),  # "pending", "approved", "rejected"
        default="pending",
        nullable=False,
        index=True,
    )
    decision_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    agent_run: Mapped["AgentRun"] = relationship(
        "AgentRun",
        back_populates="approvals",
    )

    def __repr__(self) -> str:
        return f"<ApprovalRequest(id={self.id}, tool='{self.tool_name}', status='{self.status}')>"

