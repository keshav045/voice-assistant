"""Task management tools matching database schema."""

from typing import Any, Dict, Optional
from db.models import db_add_task, db_list_tasks, db_complete_task


def add_task(title: str, due_date: Optional[str] = None, priority: Optional[str] = None) -> Dict[str, Any]:
    """Add a new to-do item or task.
    
    No confirmation needed for single add.
    """
    task = db_add_task(title=title, due_at=due_date)
    due_str = f" due on {due_date}" if due_date else ""
    return {
        "success": True,
        "task": task,
        "spoken": f"Added task: '{title}'{due_str}.",
    }


def list_tasks(status: Optional[str] = "pending") -> Dict[str, Any]:
    """List to-do tasks from the task database.
    
    Filter by status: 'pending' or 'completed'.
    """
    tasks = db_list_tasks(status=status)
    count = len(tasks)
    if count == 0:
        return {"success": True, "count": 0, "tasks": [], "spoken": f"You have no {status or ''} tasks."}

    titles = [t["title"] for t in tasks[:3]]
    preview = ", ".join(titles)
    extra = f" and {count - 3} more" if count > 3 else ""
    spoken = f"You have {count} {status or ''} task{'s' if count > 1 else ''}: {preview}{extra}."
    return {"success": True, "count": count, "tasks": tasks, "spoken": spoken}


def complete_task(id: Optional[str] = None, task_id: Optional[str] = None) -> Dict[str, Any]:
    """Mark a task done by ID or title keyword."""
    target = id or task_id or ""
    ok = db_complete_task(task_id=target)
    if ok:
        return {"success": True, "task_id": target, "spoken": f"Marked task '{target}' as completed."}
    return {"success": False, "task_id": target, "spoken": f"Could not find task '{target}' to complete."}
