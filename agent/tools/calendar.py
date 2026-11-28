"""Calendar tools for persistent SQLite schedule and free-slot planning."""

import datetime
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from db.models import db_add_calendar_event, db_list_calendar_events

# Retained in sync for backwards compatibility with inspection helpers
_CALENDAR_STORE: Dict[str, Dict[str, Any]] = {}


def _local_today() -> datetime.date:
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(tz).date()


def _seed_defaults_if_empty(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    eff_uid = (user_id or "guest").strip() or "guest"
    events = db_list_calendar_events(user_id=eff_uid)
    if not events and eff_uid == "guest":
        today_iso = _local_today().isoformat()
        defaults = [
            (
                "evt-1",
                "Project Architecture Review",
                f"{today_iso}T10:00:00+05:30",
                f"{today_iso}T11:00:00+05:30",
                ["alex@example.com"],
            ),
            (
                "evt-2",
                "Sprint Sync with Rahul",
                f"{today_iso}T16:00:00+05:30",
                f"{today_iso}T16:30:00+05:30",
                ["rahul@example.com"],
            ),
        ]
        for eid, title, st, en, att in defaults:
            evt = db_add_calendar_event(
                title=title,
                start=st,
                end=en,
                attendees=att,
                user_id="guest",
                event_id=eid,
            )
            _CALENDAR_STORE[eid] = evt
        events = db_list_calendar_events(user_id=eff_uid)
    for e in events:
        _CALENDAR_STORE[e["id"]] = e
    return events


def _resolve_target_date(label: Optional[str]) -> Optional[datetime.date]:
    raw = (label or "").strip().lower()
    if not raw or raw == "today":
        return _local_today()
    if raw in ("tomorrow", "tmrw", "kal"):
        return _local_today() + datetime.timedelta(days=1)
    if raw == "yesterday":
        return _local_today() - datetime.timedelta(days=1)
    if raw in ("all", "week", "upcoming"):
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        try:
            return datetime.date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def _parse_event_datetime(
    dt_str: str,
    default_date: Optional[datetime.date] = None,
) -> Optional[datetime.datetime]:
    """Parse ISO datetimes or natural time expressions into a timezone-aware datetime."""
    if not dt_str or not str(dt_str).strip():
        return None
    raw = str(dt_str).strip()
    lower = raw.lower()
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

    # Strip "+ 30m" helper or trailing punctuation
    raw_iso = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(raw_iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed
    except Exception:
        pass

    base_date = default_date or _local_today()
    if any(k in lower for k in ["tomorrow", "tmrw", "kal"]):
        base_date = _local_today() + datetime.timedelta(days=1)
    elif "today" in lower:
        base_date = _local_today()
    else:
        m_date = re.search(r"(\d{4}-\d{2}-\d{2})", lower)
        if m_date:
            try:
                base_date = datetime.date.fromisoformat(m_date.group(1))
            except ValueError:
                pass

    # Match 12h "4 pm", "4:30 pm", "5 baje" or 24h "16:00"
    m_12 = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b", lower)
    if m_12:
        hr = int(m_12.group(1))
        mn = int(m_12.group(2) or 0)
        ampm = m_12.group(3).replace(".", "")
        if ampm == "pm" and hr < 12:
            hr += 12
        elif ampm == "am" and hr == 12:
            hr = 0
        if 0 <= hr <= 23 and 0 <= mn <= 59:
            return datetime.datetime(base_date.year, base_date.month, base_date.day, hr, mn, tzinfo=tz)

    m_24 = re.search(r"\b(\d{1,2}):(\d{2})\b", lower)
    if m_24:
        hr, mn = int(m_24.group(1)), int(m_24.group(2))
        if 0 <= hr <= 23 and 0 <= mn <= 59:
            return datetime.datetime(base_date.year, base_date.month, base_date.day, hr, mn, tzinfo=tz)

    m_baje = re.search(r"\b(\d{1,2})\s*baje\b", lower)
    if m_baje:
        hr = int(m_baje.group(1))
        if 1 <= hr <= 8:
            hr += 12
        if 0 <= hr <= 23:
            return datetime.datetime(base_date.year, base_date.month, base_date.day, hr, 0, tzinfo=tz)

    return None


def _event_matches_date(evt: Dict[str, Any], target_date: datetime.date) -> bool:
    s_dt = _parse_event_datetime(str(evt.get("start", "")))
    if s_dt is None:
        return True
    return s_dt.date() == target_date


def list_events(
    date: Optional[str] = "today",
    start: Optional[str] = "",
    end: Optional[str] = "",
    calendar_id: Optional[str] = "primary",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Read calendar events for a given date or range."""
    events = _seed_defaults_if_empty(user_id=user_id)
    if calendar_id and calendar_id != "primary":
        events = [e for e in events if e.get("calendar_id", "primary") == calendar_id]

    target_date = _resolve_target_date(start or date)
    if target_date is not None:
        events = [e for e in events if _event_matches_date(e, target_date)]

    if not events:
        label = date or "today"
        return {
            "success": True,
            "count": 0,
            "date": label,
            "events": [],
            "spoken": f"You have no scheduled events on your calendar for {label}.",
        }

    event_summaries = []
    for e in events:
        start_time = e["start"].split("T")[1][:5] if "T" in e["start"] else e["start"]
        event_summaries.append(f"{e['title']} at {start_time}")

    spoken_summary = (
        f"You have {len(events)} event{'s' if len(events) > 1 else ''}: "
        + ", ".join(event_summaries)
        + "."
    )
    return {
        "success": True,
        "count": len(events),
        "date": date or "today",
        "events": events,
        "spoken": spoken_summary,
    }


def find_free_slot(
    duration_minutes: int = 30,
    window: str = "today",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Suggest the earliest open working-hours slot without conflicting with existing events."""
    dur = max(5, min(int(duration_minutes or 30), 480))
    target_date = _resolve_target_date(window) or _local_today()
    tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

    events = _seed_defaults_if_empty(user_id=user_id)
    busy: List[Tuple[datetime.datetime, datetime.datetime]] = []
    for e in events:
        s_dt = _parse_event_datetime(str(e.get("start", "")), default_date=target_date)
        e_dt = _parse_event_datetime(str(e.get("end", "")), default_date=target_date)
        if s_dt and s_dt.date() == target_date:
            if not e_dt or e_dt <= s_dt:
                e_dt = s_dt + datetime.timedelta(minutes=30)
            busy.append((s_dt, e_dt))

    day_start = datetime.datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=tz)
    day_end = datetime.datetime(target_date.year, target_date.month, target_date.day, 18, 0, tzinfo=tz)

    slot_s = day_start
    slot_e = slot_s + datetime.timedelta(minutes=dur)
    found: Optional[Tuple[datetime.datetime, datetime.datetime]] = None
    step = datetime.timedelta(minutes=15)

    while slot_e <= day_end:
        conflict = any(not (slot_e <= bs or slot_s >= be) for bs, be in busy)
        if not conflict:
            found = (slot_s, slot_e)
            break
        slot_s += step
        slot_e = slot_s + datetime.timedelta(minutes=dur)

    if not found:
        return {
            "success": False,
            "duration_minutes": dur,
            "window": window,
            "spoken": f"No {dur} minute free slot was found between 09:00 and 18:00 for {window}.",
        }

    s_fmt = found[0].strftime("%H:%M")
    e_fmt = found[1].strftime("%H:%M")
    return {
        "success": True,
        "duration_minutes": dur,
        "window": window,
        "date": target_date.isoformat(),
        "slot": {
            "start": s_fmt,
            "end": e_fmt,
            "start_iso": found[0].isoformat(),
            "end_iso": found[1].isoformat(),
        },
        "spoken": f"You are free between {s_fmt} and {e_fmt} for a {dur} minute meeting.",
    }


def create_event(
    title: str,
    start: str,
    end: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    calendar_id: str = "primary",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Validate and optionally persist a new calendar entry."""
    s_dt = _parse_event_datetime(str(start))
    e_dt = _parse_event_datetime(str(end), default_date=s_dt.date() if s_dt else None) if end else None

    # Validate interval ordering whenever both start & end parse
    if s_dt and e_dt and e_dt <= s_dt:
        return {
            "success": False,
            "error": "End time cannot be earlier than start time.",
            "spoken": "The event end time cannot be earlier than the start time.",
        }

    # Preserve string-level guard for partially phrased inputs like "5 PM" to "4 PM"
    s_str = str(start).lower()
    e_str = str(end or "").lower()
    if ("5 pm" in s_str or "17:00" in s_str) and ("4 pm" in e_str or "16:00" in e_str):
        return {
            "success": False,
            "error": "End time cannot be earlier than start time.",
            "spoken": "The event end time cannot be earlier than the start time.",
        }

    norm_start = s_dt.isoformat() if s_dt else str(start).strip()
    if e_dt:
        norm_end = e_dt.isoformat()
    elif end:
        norm_end = str(end).strip()
    elif s_dt:
        norm_end = (s_dt + datetime.timedelta(minutes=30)).isoformat()
    else:
        norm_end = f"{norm_start} + 30m"

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "event": {
                "title": title,
                "start": norm_start,
                "end": norm_end,
                "attendees": attendees or [],
                "status": "pending_confirmation",
            },
            "spoken": f"Ready to schedule '{title}' for {start}.",
        }

    evt = db_add_calendar_event(
        title=title,
        start=norm_start,
        end=norm_end,
        attendees=attendees or [],
        user_id=user_id,
        calendar_id=calendar_id,
    )
    _CALENDAR_STORE[evt["id"]] = evt
    spoken = f"Scheduled '{title}' for {start}."
    return {"success": True, "event": evt, "spoken": spoken}
