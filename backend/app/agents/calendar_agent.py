"""Specialist Calendar Agent with Google Calendar integration and conflict detection."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.calendar import CalendarEvent
from app.services.calendar_service import CalendarService


class CalendarAgent:
    """Specialist agent for scheduling meetings, availability queries, and agenda management."""

    def __init__(self):
        self.service = CalendarService()

    async def list_events(
        self,
        db: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[CalendarEvent]:
        """List upcoming calendar events within a specified window (defaults to next 7 days)."""
        now = datetime.now(timezone.utc)
        start = start_time or (now - timedelta(hours=2))
        end = end_time or (now + timedelta(days=7))

        stmt = (
            select(CalendarEvent)
            .where(
                CalendarEvent.status != "cancelled",
                CalendarEvent.end_time >= start,
                CalendarEvent.start_time <= end,
            )
            .order_by(CalendarEvent.start_time.asc())
        )
        if user_id:
            stmt = stmt.where(CalendarEvent.user_id == user_id)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def check_availability(
        self,
        db: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Check whether the user is free or has conflicting appointments."""
        return await self.service.check_availability(
            db=db,
            start_time=start_time,
            end_time=end_time,
            user_id=user_id,
        )

    async def get_free_slots(
        self,
        db: AsyncSession,
        target_date: Optional[datetime] = None,
        slot_duration_minutes: int = 30,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Return available time slots for booking meetings on a target date."""
        date_to_check = target_date or datetime.now(timezone.utc)
        return await self.service.find_free_slots(
            db=db,
            target_date=date_to_check,
            slot_duration_minutes=slot_duration_minutes,
            user_id=user_id,
        )

    async def create_event(
        self,
        db: AsyncSession,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = "",
        location: Optional[str] = "",
        attendees: Optional[List[str]] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> CalendarEvent:
        """Create a new calendar event (Sensitive operation gated by human approval)."""
        # Ensure UTC timezone awareness
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        event = CalendarEvent(
            title=title,
            description=description,
            location=location,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees or [],
            status="confirmed",
            user_id=user_id,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    async def update_event(
        self,
        db: AsyncSession,
        event_id: uuid.UUID,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> Optional[CalendarEvent]:
        """Update an existing calendar event (Sensitive operation)."""
        stmt = select(CalendarEvent).where(CalendarEvent.id == event_id)
        result = await db.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            return None

        if title is not None:
            event.title = title
        if start_time is not None:
            event.start_time = start_time.replace(tzinfo=timezone.utc) if start_time.tzinfo is None else start_time
        if end_time is not None:
            event.end_time = end_time.replace(tzinfo=timezone.utc) if end_time.tzinfo is None else end_time
        if description is not None:
            event.description = description
        if location is not None:
            event.location = location
        if attendees is not None:
            event.attendees = attendees
        if status is not None:
            event.status = status

        event.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(event)
        return event

    async def delete_event(
        self,
        db: AsyncSession,
        event_id: uuid.UUID,
    ) -> bool:
        """Cancel or remove a calendar event (Sensitive operation)."""
        stmt = select(CalendarEvent).where(CalendarEvent.id == event_id)
        result = await db.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            return False

        event.status = "cancelled"
        event.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return True

