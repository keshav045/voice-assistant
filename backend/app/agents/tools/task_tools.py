"""Typed tools for task management."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --- Typed Input Schemas ---
class CreateTaskInput(BaseModel):
    title: str = Field(..., description="Title of the task")
    description: Optional[str] = Field(default="", description="Detailed description")
    priority: str = Field(default="medium", description="Priority level: low, medium, high, urgent")
    due_date: Optional[str] = Field(default=None, description="Due date string in YYYY-MM-DD format")


class ListTasksInput(BaseModel):
    status: Optional[str] = Field(default=None, description="Filter by status: pending, in_progress, completed")


class DeleteTaskInput(BaseModel):
    task_id: str = Field(..., description="UUID or ID of the task to delete")


# In-memory store for Phase 3 prototype, persisting across runs
_TASK_STORE: Dict[str, Dict[str, Any]] = {
    "task-sample-1": {
        "id": "task-sample-1",
        "title": "Review Nexus Architecture Documentation",
        "description": "Examine Phase 1 to Phase 10 implementation plan specifications.",
        "priority": "high",
        "status": "in_progress",
        "due_date": "2026-11-05",
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    "task-sample-2": {
        "id": "task-sample-2",
        "title": "Prepare Weekly Team Standup Notes",
        "description": "Summarize sprint milestones and agent performance metrics.",
        "priority": "medium",
        "status": "pending",
        "due_date": "2026-11-02",
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
}


def create_task(title: str, description: Optional[str] = "", priority: str = "medium", due_date: Optional[str] = None) -> Dict[str, Any]:
    """Create a new task record."""
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    task = {
        "id": task_id,
        "title": title,
        "description": description or "",
        "priority": priority,
        "status": "pending",
        "due_date": due_date,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TASK_STORE[task_id] = task
    return {"success": True, "task": task, "message": f"Task '{title}' created successfully with ID {task_id}."}


def list_tasks(status: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve all tasks, optionally filtered by status."""
    tasks = list(_TASK_STORE.values())
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    return {
        "success": True,
        "count": len(tasks),
        "tasks": tasks,
    }


def get_task_details(task_id: str) -> Dict[str, Any]:
    """Get details for a specific task."""
    task = _TASK_STORE.get(task_id)
    if not task:
        return {"success": False, "error": f"Task with ID '{task_id}' not found."}
    return {"success": True, "task": task}


def delete_task(task_id: str) -> Dict[str, Any]:
    """Delete a task (Sensitive destructive action)."""
    if task_id not in _TASK_STORE:
        return {"success": False, "error": f"Task with ID '{task_id}' not found."}
    deleted = _TASK_STORE.pop(task_id)
    return {
        "success": True,
        "deleted_id": task_id,
        "message": f"Task '{deleted.get('title')}' successfully deleted.",
    }
