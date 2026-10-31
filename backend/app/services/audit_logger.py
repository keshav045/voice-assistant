"""Security and Compliance Audit Logging Service."""

import collections
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("nexus.audit")


class AuditLogger:
    """Manages compliance audit logs for security reviews and policy enforcement tracking."""

    def __init__(self, max_records: int = 500):
        self._records: collections.deque = collections.deque(maxlen=max_records)

    def log_event(
        self,
        event_type: str,  # "policy_eval", "tool_exec", "approval_decision", "auth_login", "auth_register", "desktop_exec"
        action: str,
        status: str,  # "allowed", "blocked", "approved", "rejected", "success", "error"
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record an audit event."""
        event = {
            "id": f"audit-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "action": action,
            "status": status,
            "user_id": user_id,
            "client_ip": client_ip,
            "details": details or {},
        }
        self._records.appendleft(event)
        logger.info(f"[AUDIT] {event_type.upper()} | {action} | status={status} | user={user_id}")
        return event

    def get_events(
        self,
        limit: int = 50,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query recent audit events with optional filters."""
        results = list(self._records)
        if event_type:
            results = [r for r in results if r["event_type"] == event_type]
        if status:
            results = [r for r in results if r["status"] == status]
        return results[:limit]


# Global singleton instance
audit_logger = AuditLogger()

