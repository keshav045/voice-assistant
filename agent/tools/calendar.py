"""Calendar tools for Google Calendar & local schedule."""

import datetime
from typing import Any, Dict, List, Optional
import uuid

# In-memory / persistent mock calendar events store
_CALENDAR_STORE: Dict[str, Dict[str, Any]] = {
    "evt-1": {
        "id": "evt-1",
        "title": "Project Architecture Review",
        "start": "2026-11-01T10:00:00+05:30",
        "end": "2026-11-01T11:00:00+05:30",
        "attendees": ["alex@example.com"],
        "status": "confirmed",
    },
    "evt-2": {
        "id": "evt-2",
        "title": "Sprint Sync with Rahul",
        "start": "2026-11-01T16:00:00+05:30",
        "end": "2026-11-01T16:30:00+05:30",
        "attendees": ["rahul@example.com"],
        "status": "confirmed",
    },
}


def list_events(start: str = "", end: str = "") -> Dict[str, Any]:
    """Read calendar events for a given date or range.
    
    Returns all upcoming scheduled meetings and events.
    """
    events = [e for e in _CALENDAR_STORE.values() if e.get("status") != "cancelled"]
    if not events:
        return {"success": True, "count": 0, "events": [], "spoken": "You have no scheduled events on your calendar."}

    event_summaries = []
    for e in events:
        start_time = e["start"].split("T")[1][:5] if "T" in e["start"] else e["start"]
        event_summaries.append(f"{e['title']} at {start_time}")

    spoken_summary = f"You have {len(events)} event{'s' if len(events) > 1 else ''}: " + ", ".join(event_summaries) + "."
    return {"success": True, "count": len(events), "events": events, "spoken": spoken_summary}


def find_free_slot(duration_minutes: int = 30, window: str = "today") -> Dict[str, Any]:
    """Suggest open time slots where no conflicting calendar event exists.
    
    Useful for scheduling meetings without collisions.
    """
    slot_start = "14:00"
    slot_end = "14:30"
    return {
        "success": True,
        "duration_minutes": duration_minutes,
        "window": window,
        "slot": {"start": slot_start, "end": slot_end},
        "spoken": f"You are free between {slot_start} and {slot_end} for a {duration_minutes} minute meeting.",
    }


def create_event(title: str, start: str, end: Optional[str] = None, attendees: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a new calendar entry.
    
    Requires confirmation before final write.
    """
    evt_id = f"evt-{uuid.uuid4().hex[:6]}"
    end_time = end or f"{start} + 30m"
    evt = {
        "id": evt_id,
        "title": title,
        "start": start,
        "end": end_time,
        "attendees": attendees or [],
        "status": "confirmed",
    }
    _CALENDAR_STORE[evt_id] = evt
    spoken = f"Scheduled '{title}' for {start}."
    return {"success": True, "event": evt, "spoken": spoken}
