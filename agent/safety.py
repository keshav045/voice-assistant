"""Safety layer, prompt injection protection, and tool validation.

Per PDF implementation plan:
  - Confirmation policy: read-only tools run directly; write tools require confirmation.
  - Guardrails: argument validation, error formatting.
  - Prompt-injection protection: text from web pages and PDFs is treated as untrusted data,
    never instructions. It cannot execute write tools without user confirmation.
"""

import re
from typing import Any, Dict, List, Set

# Write / mutating tools that require explicit user confirmation (unified with confirm.GATED_TOOLS)
WRITE_TOOLS: Set[str] = {
    "create_event",
    "send_email",
    "delete_task",
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


# --------------------------------------------------------------------------- #
# Toxicity, Profanity & Harm Prevention System
# --------------------------------------------------------------------------- #
TOXIC_PATTERNS = [
    r"\b(kill\s+yourself|kys|commit\s+suicide|die\s+in\s+a\s+fire)\b",
    r"\b(how\s+to\s+(build|make|manufacture)\s+(a\s+)?(bomb|weapon|explosive|anthrax))\b",
    r"\b(f[\*u]ck\s+you|b[\*i]tch|bastard|asshole|idiot|retard)\b",
    r"\b(hate\s+(all\s+)?(black|white|jew|muslim|asian|gay|trans)\b)",
    r"\b(genocide|white\s+supremacy|terrorist\s+attack\s+guide)\b",
]


def check_toxicity(text: str) -> Dict[str, Any]:
    """Inspect text for toxic phrases, hate speech, threats, harassment, and severe profanity.
    Returns:
        dict: {"is_toxic": bool, "category": str, "sanitized": str}
    """
    if not text or not isinstance(text, str):
        return {"is_toxic": False, "category": "clean", "sanitized": text}

    lower = text.lower()
    for pattern in TOXIC_PATTERNS:
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        if match:
            return {
                "is_toxic": True,
                "category": "harmful_content",
                "matched_pattern": match.group(0),
                "sanitized": "I cannot fulfill this request. I am designed to be a safe, helpful, and respectful AI assistant.",
            }

    return {"is_toxic": False, "category": "clean", "sanitized": text}
