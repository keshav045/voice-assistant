"""Reminders management REST API endpoints."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.task_agent import ReminderAgent
from app.database.session import get_db
from app.services.scheduler import ReminderScheduler

router = APIRouter()


class ReminderCreate(BaseModel):
    title: str
    scheduled_at: datetime
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    task_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    channel: str = "in_app"


class ReminderResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    title: str
    scheduled_at: datetime
    is_recurring: bool
    recurrence_rule: Optional[str] = None
    status: str
    triggered_at: Optional[datetime] = None
    notification_channel: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    rem_in: ReminderCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Schedule a one-time or recurring reminder."""
    reminder = await ReminderAgent.create_reminder(
        db=db,
        title=rem_in.title,
        scheduled_at=rem_in.scheduled_at,
        is_recurring=rem_in.is_recurring,
        recurrence_rule=rem_in.recurrence_rule,
        task_id=rem_in.task_id,
        user_id=rem_in.user_id,
        channel=rem_in.channel,
    )
    return reminder


@router.get("", response_model=List[ReminderResponse])
async def list_reminders(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List scheduled, triggered, or dismissed reminders."""
    reminders = await ReminderAgent.list_reminders(db=db, status=status_filter)
    return reminders


@router.post("/{reminder_id}/dismiss")
async def dismiss_reminder(
    reminder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Dismiss a triggered reminder."""
    success = await ReminderAgent.dismiss_reminder(db=db, reminder_id=reminder_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"success": True, "message": f"Reminder {reminder_id} dismissed."}


@router.post("/check-due")
async def trigger_due_check(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger an immediate scan and evaluation of due reminders."""
    triggered = await ReminderScheduler.process_due_reminders(db=db)
    return {
        "success": True,
        "triggered_count": len(triggered),
        "triggered_reminders": triggered,
    }
