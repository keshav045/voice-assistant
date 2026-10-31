"""Integration tests for Phase 4: Tasks, Reminders, and Scheduler."""

from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from app.database.session import init_db
from app.main import app
from app.services.scheduler import ReminderScheduler, compute_next_recurrence


@pytest.fixture(autouse=True)
async def setup_database():
    """Ensure database tables are initialized before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_task_crud_lifecycle():
    """Test creating, reading, updating, completing, and deleting tasks."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Task
        due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        create_res = await client.post(
            "/api/v1/tasks",
            json={
                "title": "Prepare Sprint Demo",
                "description": "Showcase Phase 4 Tasks and Reminders Engine.",
                "priority": "high",
                "due_date": due,
                "tags": ["sprint", "demo"],
            },
        )
        assert create_res.status_code == 201
        task = create_res.json()
        assert task["title"] == "Prepare Sprint Demo"
        assert task["priority"] == "high"
        assert task["status"] == "pending"
        task_id = task["id"]

        # 2. List Tasks
        list_res = await client.get("/api/v1/tasks?status=pending")
        assert list_res.status_code == 200
        tasks = list_res.json()
        assert any(t["id"] == task_id for t in tasks)

        # 3. Update Task
        update_res = await client.put(
            f"/api/v1/tasks/{task_id}",
            json={"priority": "urgent", "status": "in_progress"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["priority"] == "urgent"
        assert update_res.json()["status"] == "in_progress"

        # 4. Complete Task
        comp_res = await client.post(f"/api/v1/tasks/{task_id}/complete")
        assert comp_res.status_code == 200
        comp_task = comp_res.json()
        assert comp_task["status"] == "completed"
        assert comp_task["completed_at"] is not None

        # 5. Delete Task
        del_res = await client.delete(f"/api/v1/tasks/{task_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # Verify not found
        get_res = await client.get(f"/api/v1/tasks/{task_id}")
        assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_daily_task_summary():
    """Test daily task summary digest generation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a pending task
        await client.post(
            "/api/v1/tasks",
            json={"title": "Urgent Server Migration", "priority": "urgent"},
        )

        res = await client.get("/api/v1/tasks/summary/daily")
        assert res.status_code == 200
        data = res.json()
        assert "total_tasks" in data
        assert "completed_count" in data
        assert "pending_count" in data
        assert "urgent_tasks" in data


@pytest.mark.asyncio
async def test_reminder_due_trigger():
    """Test scheduled reminder triggering when due."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a reminder scheduled in the past
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        create_res = await client.post(
            "/api/v1/reminders",
            json={
                "title": "Review PR #42",
                "scheduled_at": past_time,
                "is_recurring": False,
            },
        )
        assert create_res.status_code == 201
        rem_id = create_res.json()["id"]

        # 2. Trigger check-due
        check_res = await client.post("/api/v1/reminders/check-due")
        assert check_res.status_code == 200
        data = check_res.json()
        assert data["triggered_count"] >= 1
        assert any(r["reminder_id"] == rem_id for r in data["triggered_reminders"])

        # 3. Verify reminder status is now 'triggered'
        list_res = await client.get("/api/v1/reminders?status=triggered")
        assert list_res.status_code == 200
        triggered_list = list_res.json()
        assert any(r["id"] == rem_id for r in triggered_list)


@pytest.mark.asyncio
async def test_recurring_reminder_next_computation():
    """Test recurring reminder recurrence rule computation and scheduling."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a recurring reminder (daily)
        past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        create_res = await client.post(
            "/api/v1/reminders",
            json={
                "title": "Daily Standup Meeting",
                "scheduled_at": past_time.isoformat(),
                "is_recurring": True,
                "recurrence_rule": "daily",
            },
        )
        assert create_res.status_code == 201
        original_id = create_res.json()["id"]

        # Process due reminders
        await ReminderScheduler.process_due_reminders()

        # Query all scheduled reminders to verify the new recurring occurrence was created
        sched_res = await client.get("/api/v1/reminders?status=scheduled")
        assert sched_res.status_code == 200
        scheduled_reminders = sched_res.json()

        # Should find a newly scheduled daily standup reminder
        matching = [r for r in scheduled_reminders if r["title"] == "Daily Standup Meeting"]
        assert len(matching) >= 1
        new_occurrence = matching[0]
        assert new_occurrence["id"] != original_id
        assert new_occurrence["status"] == "scheduled"
        assert new_occurrence["is_recurring"] is True
