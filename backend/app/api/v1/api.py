"""API v1 Router aggregation."""

from fastapi import APIRouter
from app.api.v1.endpoints import (
    approvals,
    auth,
    calendar,
    chat,
    conversations,
    emails,
    health,
    reminders,
    system,
    tasks,
    voice,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(reminders.router, prefix="/reminders", tags=["reminders"])
api_router.include_router(emails.router, prefix="/emails", tags=["emails"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["calendar"])

