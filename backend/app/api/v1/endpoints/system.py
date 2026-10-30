"""System configuration and metadata endpoint."""

from typing import Any, Dict
from fastapi import APIRouter
from app.core.config import settings

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
        ],
    }
