"""Google Calendar Integration and Availability Service with live Google API sync."""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import decrypt_oauth_token, encrypt_oauth_token
from app.models.calendar import CalendarEvent
from app.models.user import OAuthAccount

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

    @classmethod
    async def get_valid_google_token(
        cls,
        db: AsyncSession,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[str]:
        """Retrieve and auto-refresh the Google OAuth access token if needed."""
        stmt = select(OAuthAccount).where(OAuthAccount.provider == "google")
        if user_id:
            stmt = stmt.where(OAuthAccount.user_id == user_id)

        result = await db.execute(stmt)
        oa = result.scalars().first()
        if not oa or not oa.encrypted_access_token:
            return None

        now = datetime.now(timezone.utc)
        if oa.expires_at and oa.expires_at <= (now + timedelta(seconds=60)) and oa.encrypted_refresh_token:
            refresh_token = decrypt_oauth_token(oa.encrypted_refresh_token)
            if refresh_token and settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            "https://oauth2.googleapis.com/token",
                            data={
                                "client_id": settings.GOOGLE_CLIENT_ID,
                                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                                "refresh_token": refresh_token,
                                "grant_type": "refresh_token",
                            },
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            new_access = data["access_token"]
                            oa.encrypted_access_token = encrypt_oauth_token(new_access)
                            oa.expires_at = now + timedelta(seconds=data.get("expires_in", 3600))
                            await db.commit()
                            return new_access
                except Exception as e:
                    logger.warning(f"Google Calendar OAuth token refresh failed: {e}")

        return decrypt_oauth_token(oa.encrypted_access_token)

    @classmethod
    async def create_google_event(
        cls,
        db: AsyncSession,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[str]:
        """Create a live event in Google Calendar if account is connected."""
        token = await cls.get_valid_google_token(db=db, user_id=user_id)
        if not token:
            return None

        try:
            event_body = {
                "summary": title,
                "description": description or "",
                "location": location or "",
                "start": {"dateTime": start_time.isoformat()},
                "end": {"dateTime": end_time.isoformat()},
            }
            if attendees:
                event_body["attendees"] = [{"email": a} for a in attendees]

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={"Authorization": f"Bearer {token}"},
                    json=event_body,
                )
                if resp.status_code in (200, 201):
                    res_json = resp.json()
                    logger.info(f"Created live Google Calendar event: {res_json.get('id')}")
                    return res_json.get("id")
        except Exception as e:
            logger.warning(f"Live Google Calendar event creation failed: {e}")

        return None

    @classmethod
    async def delete_google_event(
        cls,
        db: AsyncSession,
        google_event_id: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Delete an event from Google Calendar by Google event ID."""
        token = await cls.get_valid_google_token(db=db, user_id=user_id)
        if not token or not google_event_id:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{google_event_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Live Google Calendar event deletion failed: {e}")
            return False

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

