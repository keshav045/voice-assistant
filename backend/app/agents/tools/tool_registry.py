"""Tool Registry and execution dispatcher for Agent tools."""

import time
import logging
from typing import Any, Callable, Dict, List
from app.agents.tools.task_tools import (
    create_task,
    delete_task,
    get_task_details,
    list_tasks,
)

logger = logging.getLogger("nexus.tools.registry")

# Available tools map
TOOLS_CATALOG: Dict[str, Callable[..., Any]] = {
    "create_task": create_task,
    "list_tasks": list_tasks,
    "get_task_details": get_task_details,
    "delete_task": delete_task,
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
