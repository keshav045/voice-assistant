"""Confirmation and read-back helper for gated write actions."""

import re
from typing import Any, Dict, Optional

GATED_TOOLS = {"create_event", "send_email", "delete_task", "delete_calendar_event"}

AFFIRMATIVE_WORDS = ["yes", "yeah", "yep", "sure", "confirm", "confirmed", "proceed", "do it", "go ahead", "send it", "book it", "please"]
NEGATIVE_WORDS = ["no", "nope", "cancel", "cancelled", "don't", "stop", "nevermind", "abort", "wait", "do not"]


def requires_confirmation(tool_name: str) -> bool:
    """Check if tool call modifies external state and requires confirmation."""
    return tool_name in GATED_TOOLS


def format_read_back(tool_name: str, args: Dict[str, Any]) -> str:
    """Generate natural spoken read-back question for confirmation."""
    if tool_name == "create_event":
        title = args.get("title", "Event")
        start = args.get("start") or args.get("start_time") or args.get("when", "")
        attendees = args.get("attendees", [])
        if isinstance(attendees, list):
            attendee_str = ", ".join(attendees)
        else:
            attendee_str = str(attendees)
        attendee_part = f" with {attendee_str}" if attendee_str else ""
        return f"I am ready to schedule '{title}' for {start}{attendee_part}. Shall I confirm this booking?"

    if tool_name == "send_email":
        to = args.get("to") or args.get("recipient") or ""
        subject = args.get("subject", "")
        if to:
            return f"I am ready to send email to {to} regarding '{subject}'. Shall I send it?"
        draft_id = args.get("draft_id", "")
        return f"Ready to send email draft {draft_id}. Shall I dispatch it now?"

    if tool_name == "delete_task":
        task_id = args.get("id") or args.get("task_id", "")
        return f"Are you sure you want me to permanently delete task '{task_id}'?"

    return f"Confirm executing '{tool_name}' with these parameters, shall I?"


def is_confirmed(user_speech: str) -> Optional[bool]:
    """Parse user's spoken response to check for affirmative or negative confirmation.
    Negative signals take strict priority over affirmative keywords.
    """
    cleaned = user_speech.lower().strip()
    words = set(re.findall(r"\b\w+\b", cleaned))

    # Check negative signals first
    for neg in NEGATIVE_WORDS:
        if neg in cleaned or neg in words:
            return False

    # Check affirmative signals
    for aff in AFFIRMATIVE_WORDS:
        if aff in cleaned or aff in words:
            return True

    return None
