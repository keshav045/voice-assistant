"""Task management tools matching database schema."""

from typing import Any, Dict, Optional, Union
from db.models import db_add_task, db_list_tasks, db_complete_task, db_delete_task


def add_task(
    title: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: Optional[str] = None,
    due_at: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a new to-do item or task.
    
    No confirmation needed for single add.
    """
    if not title or not str(title).strip():
        return {
            "success": False,
            "spoken": "Please specify a task title or description to add.",
        }
    clean_title = str(title).strip()
    effective_due = due_date or due_at
    effective_prio = (priority or "medium").strip().lower()
    task = db_add_task(
        title=clean_title,
        due_at=effective_due,
        priority=effective_prio,
        user_id=user_id,
    )
    due_str = f" due on {effective_due}" if effective_due else ""
    return {
        "success": True,
        "task": task,
        "task_id": task.get("id"),
        "priority": task.get("priority", effective_prio),
        "spoken": f"Added task: '{clean_title}'{due_str}.",
    }


def list_tasks(
    status: Optional[str] = "pending",
    limit: Optional[int] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """List to-do tasks from the task database.
    
    Filter by status: 'pending' or 'completed'.
    """
    tasks = db_list_tasks(status=status, user_id=user_id)
    if limit and isinstance(limit, int) and limit > 0:
        tasks = tasks[:limit]

    count = len(tasks)
    if count == 0:
        return {"success": True, "count": 0, "tasks": [], "spoken": f"You have no {status or ''} tasks."}

    titles = [t["title"] for t in tasks[:3]]
    preview = ", ".join(titles)
    extra = f" and {count - 3} more" if count > 3 else ""
    spoken = f"You have {count} {status or ''} task{'s' if count > 1 else ''}: {preview}{extra}."
    return {"success": True, "count": count, "tasks": tasks, "spoken": spoken}


def complete_task(
    id: Optional[Union[str, int]] = None,
    task_id: Optional[Union[str, int]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Mark a task done by ID or title keyword."""
    target = str(id if id is not None else (task_id if task_id is not None else "")).strip()
    if not target:
        return {
            "success": False,
            "task_id": target,
            "spoken": "Please specify which task ID or title to mark as completed.",
        }
    ok = db_complete_task(task_id=target, user_id=user_id)
    if ok:
        return {"success": True, "task_id": target, "spoken": f"Marked task '{target}' as completed."}
    return {"success": False, "task_id": target, "spoken": f"Task '{target}' was not found. No task exists with that ID."}


def delete_task(
    id: Optional[Union[str, int]] = None,
    task_id: Optional[Union[str, int]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Permanently delete a task by ID or title keyword."""
    target = str(id if id is not None else (task_id if task_id is not None else "")).strip()
    if not target:
        return {
            "success": False,
            "task_id": target,
            "spoken": "Please specify which task ID or title to delete.",
        }
    ok = db_delete_task(task_id=target, user_id=user_id)
    if ok:
        return {"success": True, "task_id": target, "spoken": f"Deleted task '{target}'."}
    return {"success": False, "task_id": target, "spoken": f"Could not find task '{target}' to delete."}

