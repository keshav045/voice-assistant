"""Tool Registry and execution dispatcher for Agent tools."""

import asyncio
import time
import logging
from typing import Any, Callable, Dict, List
import uuid
from app.agents.tools.task_tools import (
    create_task,
    delete_task,
    get_task_details,
    list_tasks,
)
from app.services.gmail_service import SAMPLE_INBOX

logger = logging.getLogger("nexus.tools.registry")

# In-memory drafts cache
_DRAFT_STORE: Dict[str, Dict[str, Any]] = {}


# --- Email Tool Handlers ---
def search_emails(query: str = "") -> Dict[str, Any]:
    """Search inbox for emails matching query."""
    q = query.lower()
    matches = [
        m for m in SAMPLE_INBOX
        if not q or q in m["subject"].lower() or q in m["body"].lower() or q in m["sender"].lower()
    ]
    return {
        "success": True,
        "count": len(matches),
        "messages": matches,
    }


def summarize_emails(query: str = "") -> Dict[str, Any]:
    """Summarize emails matching query."""
    res = search_emails(query)
    messages = res.get("messages", [])
    if not messages:
        return {"success": True, "summary": "No matching emails found."}

    lines = [f"Summary of {len(messages)} emails:"]
    for m in messages:
        lines.append(f"• From: {m['sender']} | Subject: {m['subject']} | Details: {m['snippet']}")
    return {"success": True, "summary": "\n".join(lines), "emails_analyzed": len(messages)}


def create_email_draft(recipient: str, subject: str, body: str) -> Dict[str, Any]:
    """Create a new email draft."""
    draft_id = f"draft-{uuid.uuid4().hex[:8]}"
    draft = {
        "id": draft_id,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "status": "draft",
    }
    _DRAFT_STORE[draft_id] = draft
    return {"success": True, "draft": draft, "message": f"Draft created for '{recipient}' with subject '{subject}'."}


def send_email(recipient: str, subject: str, body: str) -> Dict[str, Any]:
    """Send an email (Sensitive operation)."""
    return {
        "success": True,
        "message": f"Email successfully dispatched to '{recipient}' with subject '{subject}'.",
        "recipient": recipient,
        "subject": subject,
    }


# --- Calendar Tool Handlers (Phase 6) ---
_CALENDAR_STORE: Dict[str, Dict[str, Any]] = {
    "evt-001": {
        "id": "evt-001",
        "title": "Nexus Architecture Review",
        "start_time": "2026-10-31T10:00:00Z",
        "end_time": "2026-10-31T11:00:00Z",
        "location": "Google Meet",
        "status": "confirmed",
    },
    "evt-002": {
        "id": "evt-002",
        "title": "Daily Product Standup",
        "start_time": "2026-10-31T11:30:00Z",
        "end_time": "2026-10-31T12:00:00Z",
        "location": "Discord Engineering Channel",
        "status": "confirmed",
    },
}


def list_calendar_events(start_date: str = "", end_date: str = "") -> Dict[str, Any]:
    """List calendar events from schedule."""
    events = list(_CALENDAR_STORE.values())
    return {
        "success": True,
        "count": len(events),
        "events": events,
    }


def check_calendar_availability(start_time: str, end_time: str) -> Dict[str, Any]:
    """Check if time slot has conflicting events."""
    conflicts = []
    for evt in _CALENDAR_STORE.values():
        if evt["status"] != "cancelled":
            if max(start_time, evt["start_time"]) < min(end_time, evt["end_time"]):
                conflicts.append(evt)
    is_free = len(conflicts) == 0
    return {
        "success": True,
        "is_free": is_free,
        "conflicts": conflicts,
        "message": "Time slot is available." if is_free else f"Conflict detected with {len(conflicts)} event(s).",
    }


def create_calendar_event(title: str, start_time: str, end_time: str, description: str = "", location: str = "") -> Dict[str, Any]:
    """Create a new calendar event (Sensitive operation)."""
    evt_id = f"evt-{uuid.uuid4().hex[:6]}"
    evt = {
        "id": evt_id,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
        "location": location,
        "status": "confirmed",
    }
    _CALENDAR_STORE[evt_id] = evt
    return {
        "success": True,
        "event": evt,
        "message": f"Calendar event '{title}' scheduled from {start_time} to {end_time}.",
    }


def delete_calendar_event(event_id: str) -> Dict[str, Any]:
    """Remove/cancel a calendar event (Sensitive operation)."""
    if event_id in _CALENDAR_STORE:
        _CALENDAR_STORE[event_id]["status"] = "cancelled"
        return {"success": True, "message": f"Calendar event '{event_id}' has been cancelled."}
    return {"success": False, "error": f"Event '{event_id}' not found."}


# Available tools map
TOOLS_CATALOG: Dict[str, Callable[..., Any]] = {
    # Task tools
    "create_task": create_task,
    "list_tasks": list_tasks,
    "get_task_details": get_task_details,
    "delete_task": delete_task,
    # Email tools (Phase 5)
    "search_emails": search_emails,
    "summarize_emails": summarize_emails,
    "create_email_draft": create_email_draft,
    "send_email": send_email,
    # Calendar tools (Phase 6)
    "list_calendar_events": list_calendar_events,
    "check_calendar_availability": check_calendar_availability,
    "create_calendar_event": create_calendar_event,
    "delete_calendar_event": delete_calendar_event,
}

# OpenAI-compatible function schemas
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task in the user's task manager.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The title or action of the task"},
                    "description": {"type": "string", "description": "Optional notes or details"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "default": "medium"},
                    "due_date": {"type": "string", "description": "Optional due date (YYYY-MM-DD)"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List all existing tasks from the task manager.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "description": "Optional status filter"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_details",
            "description": "Retrieve full details for a single task by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Permanently remove a task from the system (requires confirmation).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to delete"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search user's Gmail inbox for messages matching keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or sender name"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_emails",
            "description": "Summarize unread or recent email messages, extracting invitations and action items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional filter query"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_email_draft",
            "description": "Prepare a new email draft for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Email address of the recipient"},
                    "subject": {"type": "string", "description": "Subject of the email"},
                    "body": {"type": "string", "description": "Body content of the email"},
                },
                "required": ["recipient", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient (REQUIRES explicit human approval).",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Email address of the recipient"},
                    "subject": {"type": "string", "description": "Subject of the email"},
                    "body": {"type": "string", "description": "Body content of the email"},
                },
                "required": ["recipient", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": "List scheduled calendar events within an optional time frame.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Optional ISO start date"},
                    "end_date": {"type": "string", "description": "Optional ISO end date"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_calendar_availability",
            "description": "Check if a requested time window is free from conflicts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_time": {"type": "string", "description": "Start ISO datetime"},
                    "end_time": {"type": "string", "description": "End ISO datetime"},
                },
                "required": ["start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Schedule a new meeting or event (REQUIRES explicit human approval).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the calendar event"},
                    "start_time": {"type": "string", "description": "Start ISO datetime"},
                    "end_time": {"type": "string", "description": "End ISO datetime"},
                    "description": {"type": "string", "description": "Optional notes or agenda"},
                    "location": {"type": "string", "description": "Meeting link or physical location"},
                },
                "required": ["title", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Cancel or delete a calendar event (REQUIRES explicit human approval).",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "ID of the event to cancel"},
                },
                "required": ["event_id"],
            },
        },
    },
]


def execute_tool_call(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a registered tool and measure latency."""
    start_time = time.perf_counter()
    tool_fn = TOOLS_CATALOG.get(tool_name)

    if not tool_fn:
        return {
            "success": False,
            "error": f"Tool '{tool_name}' is not recognized in the registry.",
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }

    try:
        if asyncio.iscoroutinefunction(tool_fn):
            result = asyncio.run(tool_fn(**args))
        else:
            result = tool_fn(**args)

        latency = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "success": True,
            "result": result,
            "latency_ms": latency,
        }
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return {
            "success": False,
            "error": str(e),
            "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
        }
