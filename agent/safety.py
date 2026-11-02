"""Safety layer, prompt injection protection, and tool validation.

Per PDF implementation plan:
  - Confirmation policy: read-only tools run directly; write tools require confirmation.
  - Guardrails: argument validation, error formatting.
  - Prompt-injection protection: text from web pages and PDFs is treated as untrusted data,
    never instructions. It cannot execute write tools without user confirmation.
"""

import re
from typing import Any, Dict, List, Set

# Write / mutating tools that require explicit user confirmation
WRITE_TOOLS: Set[str] = {
    "create_event",
    "send_email",
    "complete_task",
}

# Suspicious instruction phrases that may appear in parsed text / search results
INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"disregard all previous instructions",
    r"reveal (the )?system prompt",
    r"system prompt:?",
    r"you are now in maintenance mode",
    r"send (all )?emails? to",
    r"forward (my )?notes to",
    r"delete (all )?my files",
    r"transfer.*to",
]


def is_write_action(tool_name: str) -> bool:
    """Check if tool performs a write/mutating action."""
    return tool_name in WRITE_TOOLS


def sanitize_external_text(text: str) -> str:
    """Neutralize potential prompt injections in retrieved external documents/web snippets."""
    clean = text
    for pattern in INJECTION_PATTERNS:
        clean = re.sub(pattern, "[FILTERED_INSTRUCTION]", clean, flags=re.IGNORECASE)
    return clean


def validate_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate tool arguments to prevent corrupted or malicious inputs."""
    if not isinstance(args, dict):
        raise ValueError(f"Tool arguments for '{tool_name}' must be a dictionary.")

    # Specific tool parameter validations
    if tool_name == "calculator":
        expr = args.get("expression", "")
        if not isinstance(expr, str) or not expr.strip():
            raise ValueError("Expression must be a non-empty string.")
        if len(expr) > 200:
            raise ValueError("Expression is too long.")

    elif tool_name == "create_event":
        if "title" not in args or not str(args["title"]).strip():
            raise ValueError("Event title cannot be blank.")
        if "start" not in args:
            raise ValueError("Start date/time is required.")

    elif tool_name == "send_email":
        if "draft_id" not in args and "to" not in args:
            raise ValueError("send_email requires a draft_id or recipient.")

    elif tool_name == "add_task":
        if "title" not in args or not str(args["title"]).strip():
            raise ValueError("Task title cannot be blank.")

    return args
