"""Specialist Task and Reminder Agent with DB persistence and daily digest."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.productivity import Reminder, Task


class TaskAgent:
    """Specialist agent managing persistent tasks and productivity workflows."""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        title: str,
        description: Optional[str] = "",
        priority: str = "medium",
        due_date: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Task:
        task = Task(
            title=title,
            description=description or "",
            priority=priority.lower(),
            status="pending",
            due_date=due_date,
            tags=tags or [],
            user_id=user_id,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Task]:
        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)
        if user_id:
            stmt = stmt.where(Task.user_id == user_id)
        stmt = stmt.order_by(Task.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_task(db: AsyncSession, task_id: uuid.UUID) -> Optional[Task]:
        result = await db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_task(
        db: AsyncSession,
        task_id: uuid.UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        due_date: Optional[datetime] = None,
    ) -> Optional[Task]:
        task = await TaskAgent.get_task(db, task_id)
        if not task:
            return None

        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority.lower()
        if status is not None:
            task.status = status
            if status == "completed":
                task.completed_at = datetime.now(timezone.utc)
        if due_date is not None:
            task.due_date = due_date

        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def complete_task(db: AsyncSession, task_id: uuid.UUID) -> Optional[Task]:
        return await TaskAgent.update_task(db, task_id, status="completed")

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: uuid.UUID) -> bool:
        task = await TaskAgent.get_task(db, task_id)
        if not task:
            return False
        await db.delete(task)
        await db.commit()
        return True

    @staticmethod
    async def generate_daily_summary(
        db: AsyncSession, user_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """Aggregate daily task metrics and priority highlights."""
        tasks = await TaskAgent.list_tasks(db, user_id=user_id)
        total = len(tasks)
        completed = [t for t in tasks if t.status == "completed"]
        pending = [t for t in tasks if t.status == "pending"]
        urgent = [t for t in tasks if t.priority in ["urgent", "high"] and t.status != "completed"]

        return {
            "summary_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_tasks": total,
            "completed_count": len(completed),
            "pending_count": len(pending),
            "urgent_pending_count": len(urgent),
            "urgent_tasks": [{"id": str(t.id), "title": t.title, "priority": t.priority} for t in urgent[:5]],
            "completion_rate": round((len(completed) / total * 100), 1) if total > 0 else 0.0,
        }


class ReminderAgent:
    """Specialist agent managing reminders and recurrence rules."""

    @staticmethod
    async def create_reminder(
        db: AsyncSession,
        title: str,
        scheduled_at: datetime,
        is_recurring: bool = False,
        recurrence_rule: Optional[str] = None,
        task_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        channel: str = "in_app",
    ) -> Reminder:
        reminder = Reminder(
            title=title,
            scheduled_at=scheduled_at,
            is_recurring=is_recurring,
            recurrence_rule=recurrence_rule,
            task_id=task_id,
            user_id=user_id,
            status="scheduled",
            notification_channel=channel,
        )
        db.add(reminder)
        await db.commit()
        await db.refresh(reminder)
        return reminder

    @staticmethod
    async def list_reminders(
        db: AsyncSession,
        status: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Reminder]:
        stmt = select(Reminder)
        if status:
            stmt = stmt.where(Reminder.status == status)
        if user_id:
            stmt = stmt.where(Reminder.user_id == user_id)
        stmt = stmt.order_by(Reminder.scheduled_at.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def dismiss_reminder(db: AsyncSession, reminder_id: uuid.UUID) -> bool:
        result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
        reminder = result.scalar_one_or_none()
        if not reminder:
            return False
        reminder.status = "dismissed"
        await db.commit()
        return True
