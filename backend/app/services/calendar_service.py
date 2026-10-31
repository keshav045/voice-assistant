"""Google Calendar Integration and Availability Service."""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.calendar import CalendarEvent

logger = logging.getLogger("nexus.calendar")

# Curated reference schedule for local testing and offline capability
SAMPLE_CALENDAR_EVENTS: List[Dict[str, Any]] = [
    {
        "id": "cal-sync-001",
        "title": "Nexus Agentic Architecture Review",
        "description": "Deep-dive into LangGraph 9-node execution and human approval gates.",
        "location": "Google Meet: https://meet.google.com/nex-arch-sync",
        "start_offset_hours": 1,
        "duration_hours": 1,
        "status": "confirmed",
        "attendees": ["keshav@nexus.ai", "architect@nexus.ai", "sarah@apextechnologies.io"],
    },
    {
        "id": "cal-standup-002",
        "title": "Daily Product & Engineering Standup",
        "description": "Cross-functional standup to review Phase 5 & 6 milestone deliverables.",
        "location": "Discord Engineering Channel",
        "start_offset_hours": 3,
        "duration_hours": 0.5,
        "status": "confirmed",
        "attendees": ["keshav@nexus.ai", "alex@nexus.ai", "team@nexus.ai"],
    },
    {
        "id": "cal-focus-003",
        "title": "Deep Work: Windows Companion Development",
        "description": "Block dedicated to PyWinAuto and WebSocket companion design.",
        "location": "Local Workstation",
        "start_offset_hours": 5,
        "duration_hours": 2,
        "status": "confirmed",
        "attendees": ["keshav@nexus.ai"],
    },
]


class CalendarService:
    """Manages calendar events, conflict detection, and availability slot calculation."""

    @staticmethod
    def check_interval_overlap(
        start1: datetime,
        end1: datetime,
        start2: datetime,
        end2: datetime,
    ) -> bool:
        """Return True if time intervals [start1, end1] and [start2, end2] overlap."""
        return max(start1, start2) < min(end1, end2)

    @classmethod
    async def get_events_in_range(
        cls,
        db: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[CalendarEvent]:
        """Fetch all non-cancelled events that intersect with [start_time, end_time]."""
        stmt = (
            select(CalendarEvent)
            .where(
                and_(
                    CalendarEvent.status != "cancelled",
                    CalendarEvent.start_time < end_time,
                    CalendarEvent.end_time > start_time,
                )
            )
            .order_by(CalendarEvent.start_time.asc())
        )
        if user_id:
            stmt = stmt.where(CalendarEvent.user_id == user_id)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def check_availability(
        cls,
        db: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        user_id: Optional[uuid.UUID] = None,
        exclude_event_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Check if proposed time slot has conflicts with existing events."""
        events = await cls.get_events_in_range(db, start_time, end_time, user_id=user_id)
        if exclude_event_id:
            events = [e for e in events if e.id != exclude_event_id]

        is_free = len(events) == 0
        conflicts = [
            {
                "id": str(e.id),
                "title": e.title,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "location": e.location,
            }
            for e in events
        ]

        return {
            "is_free": is_free,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "message": (
                f"Time slot from {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')} is free."
                if is_free
                else f"Conflict detected with {len(conflicts)} event(s): {', '.join([c['title'] for c in conflicts])}."
            ),
        }

    @classmethod
    async def find_free_slots(
        cls,
        db: AsyncSession,
        target_date: datetime,
        work_start_hour: int = 9,
        work_end_hour: int = 18,
        slot_duration_minutes: int = 30,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Calculate open availability windows between scheduled meetings for a given day."""
        tz = target_date.tzinfo or timezone.utc
        day_start = datetime.combine(target_date.date(), time(work_start_hour, 0), tzinfo=tz)
        day_end = datetime.combine(target_date.date(), time(work_end_hour, 0), tzinfo=tz)

        # Get all events for the entire day
        events = await cls.get_events_in_range(db, day_start, day_end, user_id=user_id)
        events.sort(key=lambda e: e.start_time)

        free_slots: List[Dict[str, Any]] = []
        current_cursor = day_start

        for event in events:
            # Ensure event start is clamped to day_start
            event_start = max(event.start_time, day_start)
            if event_start > current_cursor:
                gap = (event_start - current_cursor).total_seconds() / 60
                if gap >= slot_duration_minutes:
                    free_slots.append(
                        {
                            "start_time": current_cursor.isoformat(),
                            "end_time": event_start.isoformat(),
                            "duration_minutes": int(gap),
                            "display": f"{current_cursor.strftime('%H:%M')} - {event_start.strftime('%H:%M')} ({int(gap)} min)",
                        }
                    )
            current_cursor = max(current_cursor, min(event.end_time, day_end))

        # Check remaining gap until work_end_hour
        if current_cursor < day_end:
            gap = (day_end - current_cursor).total_seconds() / 60
            if gap >= slot_duration_minutes:
                free_slots.append(
                    {
                        "start_time": current_cursor.isoformat(),
                        "end_time": day_end.isoformat(),
                        "duration_minutes": int(gap),
                        "display": f"{current_cursor.strftime('%H:%M')} - {day_end.strftime('%H:%M')} ({int(gap)} min)",
                    }
                )

        return free_slots
