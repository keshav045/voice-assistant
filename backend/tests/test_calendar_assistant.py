"""Integration tests for Phase 6: Google Calendar Assistant & Availability Engine."""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database.session import init_db
from app.agents.policy import PolicyEngine


@pytest.fixture(autouse=True)
async def setup_database():
    """Ensure database tables are initialized before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_calendar_event_crud():
    """Test full lifecycle of creating, listing, updating, and cancelling calendar events."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        now = datetime.now(timezone.utc)
        start = now + timedelta(days=1, hours=2)
        end = start + timedelta(hours=1)

        payload = {
            "title": "Nexus Architecture Design Session",
            "description": "Discussing vector database indexing and Redis queue.",
            "location": "Meet https://meet.google.com/nex-test",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "attendees": ["keshav@nexus.ai", "architect@nexus.ai"],
        }

        # 1. Create event
        create_res = await client.post("/api/v1/calendar/events", json=payload)
        assert create_res.status_code == 201
        event = create_res.json()
        assert event["title"] == payload["title"]
        assert event["location"] == payload["location"]
        assert event["status"] == "confirmed"
        event_id = event["id"]

        # 2. List events
        list_res = await client.get("/api/v1/calendar/events")
        assert list_res.status_code == 200
        events = list_res.json()
        assert len(events) >= 1
        assert any(e["id"] == event_id for e in events)

        # 3. Update event
        update_res = await client.put(
            f"/api/v1/calendar/events/{event_id}",
            json={"title": "Nexus Architecture Design Session (Updated)", "location": "Room 402"},
        )
        assert update_res.status_code == 200
        updated = update_res.json()
        assert updated["title"] == "Nexus Architecture Design Session (Updated)"
        assert updated["location"] == "Room 402"

        # 4. Delete/cancel event
        del_res = await client.delete(f"/api/v1/calendar/events/{event_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True


@pytest.mark.asyncio
async def test_calendar_availability_and_conflicts():
    """Test conflict detection when proposed meeting overlaps with an existing event."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        now = datetime.now(timezone.utc)
        base_time = now + timedelta(days=2)
        evt_start = base_time.replace(hour=14, minute=0, second=0, microsecond=0)
        evt_end = base_time.replace(hour=15, minute=0, second=0, microsecond=0)

        # Book an event from 14:00 to 15:00
        await client.post(
            "/api/v1/calendar/events",
            json={
                "title": "Existing Team Review",
                "start_time": evt_start.isoformat(),
                "end_time": evt_end.isoformat(),
            },
        )

        # Check overlapping slot (14:30 to 15:30) -> Should report conflict
        overlap_start = base_time.replace(hour=14, minute=30, second=0, microsecond=0)
        overlap_end = base_time.replace(hour=15, minute=30, second=0, microsecond=0)
        avail_res = await client.get(
            "/api/v1/calendar/availability",
            params={"start_time": overlap_start.isoformat(), "end_time": overlap_end.isoformat()},
        )
        assert avail_res.status_code == 200
        data = avail_res.json()
        assert data["is_free"] is False
        assert data["conflict_count"] >= 1
        assert any(c["title"] == "Existing Team Review" for c in data["conflicts"])

        # Check non-overlapping slot (16:00 to 17:00) -> Should be free
        free_start = base_time.replace(hour=16, minute=0, second=0, microsecond=0)
        free_end = base_time.replace(hour=17, minute=0, second=0, microsecond=0)
        free_res = await client.get(
            "/api/v1/calendar/availability",
            params={"start_time": free_start.isoformat(), "end_time": free_end.isoformat()},
        )
        assert free_res.status_code == 200
        free_data = free_res.json()
        assert free_data["is_free"] is True
        assert free_data["conflict_count"] == 0


@pytest.mark.asyncio
async def test_find_free_slots():
    """Test calculating free availability windows throughout a workday."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        target_day = datetime.now(timezone.utc) + timedelta(days=3)
        res = await client.get(
            "/api/v1/calendar/free-slots",
            params={"date": target_day.isoformat(), "duration": 30},
        )
        assert res.status_code == 200
        slots = res.json()
        assert isinstance(slots, list)
        assert len(slots) >= 1
        assert "display" in slots[0]
        assert slots[0]["duration_minutes"] >= 30


@pytest.mark.asyncio
async def test_calendar_policy_engine_gates():
    """Verify deterministic policy engine gates calendar mutation tools while allowing reads."""
    # Safe read tools
    list_dec = PolicyEngine.evaluate("list_calendar_events", {})
    assert list_dec.allowed is True
    assert list_dec.requires_approval is False

    avail_dec = PolicyEngine.evaluate(
        "check_calendar_availability",
        {"start_time": "2026-10-31T10:00:00Z", "end_time": "2026-10-31T11:00:00Z"},
    )
    assert avail_dec.allowed is True
    assert avail_dec.requires_approval is False

    # Sensitive mutation tools
    create_dec = PolicyEngine.evaluate(
        "create_calendar_event",
        {"title": "Sync", "start_time": "2026-10-31T10:00:00Z", "end_time": "2026-10-31T11:00:00Z"},
    )
    assert create_dec.allowed is True
    assert create_dec.requires_approval is True
    assert "Create calendar" in create_dec.action_summary

    delete_dec = PolicyEngine.evaluate("delete_calendar_event", {"event_id": "evt-123"})
    assert delete_dec.allowed is True
    assert delete_dec.requires_approval is True
    assert "Delete calendar" in delete_dec.action_summary

