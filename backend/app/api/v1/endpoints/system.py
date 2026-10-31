"""System configuration and metadata endpoint."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from app.core.config import settings
from app.services.audit_logger import audit_logger

router = APIRouter()


@router.get("/config", summary="Retrieve public system configuration")
async def get_system_config() -> Dict[str, Any]:
    """Return active system configuration, model identifiers, and capabilities."""
    return {
        "project_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "api_v1_prefix": settings.API_V1_STR,
        "ai": {
            "model": settings.OPENAI_MODEL,
            "voice_model": settings.OPENAI_VOICE_MODEL,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "api_key_configured": bool(settings.OPENAI_API_KEY),
        },
        "capabilities": [
            "voice_streaming",
            "langgraph_orchestration",
            "task_management",
            "email_agent",
            "calendar_agent",
            "desktop_companion",
            "semantic_memory",
            "approval_gates",
            "audit_logging",
            "rate_limiting",
        ],
    }


@router.get("/audit-logs", summary="Retrieve security audit log records")
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """Query compliance audit trail of tool invocations, approval decisions, and authentication."""
    return audit_logger.get_events(limit=limit, event_type=event_type, status=status)


