"""Background Scheduler and Reminder Trigger Worker."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import AsyncSessionLocal
from app.models.productivity import Reminder

logger = logging.getLogger("nexus.scheduler")


def compute_next_recurrence(current_time: datetime, rule: str) -> datetime:
    """Calculate the next timestamp based on recurrence rule."""
    rule_lower = (rule or "daily").lower()
    if "daily" in rule_lower:
        return current_time + timedelta(days=1)
    elif "weekly" in rule_lower:
        return current_time + timedelta(weeks=1)
    elif "monthly" in rule_lower:
        return current_time + timedelta(days=30)
    # Default to 1 day if unrecognized
    return current_time + timedelta(days=1)


class ReminderScheduler:
    """Handles due reminder evaluation, notifications, and recurring schedules."""

    @staticmethod
    async def process_due_reminders(db: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
        """Scan and trigger all due reminders."""
        now = datetime.now(timezone.utc)
        triggered_results = []

        async def _run_process(session: AsyncSession):
            stmt = select(Reminder).where(
                Reminder.status == "scheduled",
                Reminder.scheduled_at <= now,
            )
            result = await session.execute(stmt)
            due_reminders = result.scalars().all()

            for rem in due_reminders:
                rem.status = "triggered"
                rem.triggered_at = now

                triggered_data = {
                    "reminder_id": str(rem.id),
                    "title": rem.title,
                    "task_id": str(rem.task_id) if rem.task_id else None,
                    "channel": rem.notification_channel,
                    "scheduled_at": rem.scheduled_at.isoformat(),
                    "triggered_at": now.isoformat(),
                }
                triggered_results.append(triggered_data)
                logger.info(f"🔔 Reminder triggered: '{rem.title}' (ID: {rem.id})")

                # If recurring, automatically spawn the next scheduled occurrence
                if rem.is_recurring and rem.recurrence_rule:
                    next_time = compute_next_recurrence(rem.scheduled_at, rem.recurrence_rule)
                    next_reminder = Reminder(
                        user_id=rem.user_id,
                        task_id=rem.task_id,
                        title=rem.title,
                        scheduled_at=next_time,
                        is_recurring=True,
                        recurrence_rule=rem.recurrence_rule,
                        status="scheduled",
                        notification_channel=rem.notification_channel,
                    )
                    session.add(next_reminder)
                    logger.info(f"🔁 Recurring reminder scheduled for {next_time}: '{rem.title}'")

            await session.commit()

        if db:
            await _run_process(db)
        else:
            async with AsyncSessionLocal() as session:
                await _run_process(session)

        return triggered_results


async def scheduler_background_loop(poll_interval_seconds: int = 10) -> None:
    """Continuous async background worker polling for due reminders."""
    logger.info(f"Scheduler worker started with poll interval {poll_interval_seconds}s")
    while True:
        try:
            await ReminderScheduler.process_due_reminders()
        except asyncio.CancelledError:
            logger.info("Scheduler worker stopping...")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}")

        await asyncio.sleep(poll_interval_seconds)
