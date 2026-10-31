"""Google Calendar REST API endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.calendar_agent import CalendarAgent
from app.database.session import get_db

router = APIRouter()
calendar_agent = CalendarAgent()


# --- Pydantic Schemas ---
class CalendarEventCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = ""
    location: Optional[str] = ""
    attendees: Optional[List[str]] = []
    user_id: Optional[uuid.UUID] = None


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    status: Optional[str] = None


class CalendarEventResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: datetime
    end_time: datetime
    is_all_day: bool = False
    status: str
    google_event_id: Optional[str] = None
    attendees: Optional[List[str]] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AvailabilityResponse(BaseModel):
    is_free: bool
    start_time: str
    end_time: str
    conflict_count: int
    conflicts: List[Dict[str, Any]]
    message: str


class FreeSlotResponse(BaseModel):
    start_time: str
    end_time: str
    duration_minutes: int
    display: str


def parse_dt(val: Any) -> datetime:
    """Parse string or datetime flexibly, handling ISO formats and timezone offsets."""
    if isinstance(val, datetime):
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
    if isinstance(val, str):
        s = val.strip()
        if " " in s and "+" not in s and "Z" not in s:
            s = s.replace(" ", "+")
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    raise ValueError(f"Cannot parse datetime from {val}")


# --- Endpoints ---
@router.get("/events", response_model=List[CalendarEventResponse])
async def list_events(
    start: Optional[str] = Query(None, description="Start range for events filter"),
    end: Optional[str] = Query(None, description="End range for events filter"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve scheduled calendar events within an optional time window."""
    start_dt = parse_dt(start) if start else None
    end_dt = parse_dt(end) if end else None
    return await calendar_agent.list_events(db=db, start_time=start_dt, end_time=end_dt)


@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_in: CalendarEventCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new calendar event."""
    if event_in.end_time <= event_in.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time.",
        )

    return await calendar_agent.create_event(
        db=db,
        title=event_in.title,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        description=event_in.description,
        location=event_in.location,
        attendees=event_in.attendees,
        user_id=event_in.user_id,
    )


@router.get("/availability", response_model=AvailabilityResponse)
async def check_availability(
    start_time: str = Query(..., description="Start of proposed slot"),
    end_time: str = Query(..., description="End of proposed slot"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Check whether a given time window is free from conflicts."""
    try:
        start_dt = parse_dt(start_time)
        end_dt = parse_dt(end_time)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid datetime format: {e}")

    if end_dt <= start_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time.",
        )

    return await calendar_agent.check_availability(
        db=db,
        start_time=start_dt,
        end_time=end_dt,
    )


@router.get("/free-slots", response_model=List[FreeSlotResponse])
async def get_free_slots(
    date: Optional[str] = Query(None, description="Date to query for open slots"),
    duration: int = Query(30, ge=15, le=240, description="Minimum duration in minutes"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Find available gap slots between meetings for a given workday."""
    target_dt = parse_dt(date) if date else None
    return await calendar_agent.get_free_slots(
        db=db,
        target_date=target_dt,
        slot_duration_minutes=duration,
    )



@router.put("/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: uuid.UUID,
    event_in: CalendarEventUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update an existing calendar event."""
    updated = await calendar_agent.update_event(
        db=db,
        event_id=event_id,
        title=event_in.title,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        description=event_in.description,
        location=event_in.location,
        attendees=event_in.attendees,
        status=event_in.status,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar event {event_id} not found.",
        )
    return updated


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cancel / remove a calendar event."""
    deleted = await calendar_agent.delete_event(db=db, event_id=event_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calendar event {event_id} not found.",
        )
    return {"success": True, "message": f"Event {event_id} cancelled."}
