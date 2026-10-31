"""Task management REST API endpoints."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.task_agent import TaskAgent
from app.database.session import get_db

router = APIRouter()


# --- Pydantic Schemas ---
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: str = "medium"
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = []
    user_id: Optional[uuid.UUID] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    priority: str
    status: str
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tags: Optional[List[str]] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Endpoints ---
@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new task."""
    task = await TaskAgent.create_task(
        db=db,
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority,
        due_date=task_in.due_date,
        tags=task_in.tags,
        user_id=task_in.user_id,
    )
    return task


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority_filter: Optional[str] = Query(None, alias="priority"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List tasks with optional status and priority filtering."""
    tasks = await TaskAgent.list_tasks(
        db=db,
        status=status_filter,
        priority=priority_filter,
    )
    return tasks


@router.get("/summary/daily")
async def get_daily_summary(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve daily task summary digest and urgency metrics."""
    return await TaskAgent.generate_daily_summary(db=db)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get task details by UUID."""
    task = await TaskAgent.get_task(db=db, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    task_update: TaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update task properties, status, priority, or due date."""
    updated = await TaskAgent.update_task(
        db=db,
        task_id=task_id,
        title=task_update.title,
        description=task_update.description,
        priority=task_update.priority,
        status=task_update.status,
        due_date=task_update.due_date,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Transition a task status to completed."""
    completed = await TaskAgent.complete_task(db=db, task_id=task_id)
    if not completed:
        raise HTTPException(status_code=404, detail="Task not found")
    return completed


@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a task."""
    deleted = await TaskAgent.delete_task(db=db, task_id=task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "message": f"Task {task_id} deleted successfully"}
