"""Health and diagnostic endpoint."""

from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter
from app.core.config import settings
from app.database.session import check_db_connection

router = APIRouter()


@router.get("", summary="Check system health")
async def health_check() -> Dict[str, Any]:
    """Return health status of the API and its dependent services."""
    db_status = await check_db_connection()

    is_healthy = db_status.get("status") == "connected"

    return {
        "status": "healthy" if is_healthy else "degraded",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
