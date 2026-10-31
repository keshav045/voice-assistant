"""Deterministic policy engine for agent actions and approval gating."""

from dataclasses import dataclass
from typing import Any, Dict, Set


@dataclass
class PolicyDecision:
    """Outcome of policy evaluation on a proposed tool execution."""
    allowed: bool
    requires_approval: bool
    action_summary: str
    reason: str


# Tools that can execute automatically without human-in-the-loop approval
SAFE_READ_TOOLS: Set[str] = {
    "list_tasks",
    "get_task_details",
    "search_emails",
    "read_email",
    "list_calendar_events",
    "check_calendar_availability",
    "retrieve_memory",
    "get_desktop_status",
    "get_active_window",
    "get_system_metrics",
    "search_files",
    "take_screenshot",
}


# Tools that require explicit human approval before execution
SENSITIVE_ACTION_TOOLS: Set[str] = {
    "delete_task",
    "send_email",
    "delete_email",
    "create_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "desktop_run_command",
    "desktop_delete_file",
    "wipe_memory",
}

# Strictly forbidden / prohibited actions
PROHIBITED_TOOLS: Set[str] = {
    "arbitrary_shell_exec",
    "format_disk",
    "bypass_auth",
}


class PolicyEngine:
    """Enforces deterministic security checks on tool invocations."""

    @staticmethod
    def evaluate(tool_name: str, tool_args: Dict[str, Any]) -> PolicyDecision:
        """Evaluate if an action is allowed, and if explicit approval is required."""
        if tool_name in PROHIBITED_TOOLS:
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                action_summary=f"Prohibited execution of '{tool_name}'",
                reason="This tool is strictly prohibited by security policy.",
            )

        if tool_name in SENSITIVE_ACTION_TOOLS:
            # Generate human-readable action summary for the user to approve
            summary = PolicyEngine._format_action_summary(tool_name, tool_args)
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                action_summary=summary,
                reason="Policy requires explicit user consent for destructive or external write actions.",
            )

        if tool_name in SAFE_READ_TOOLS or tool_name.startswith("safe_") or tool_name == "create_task":
            # Notice create_task is safe (can be edited/deleted), but delete_task requires approval!
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                action_summary=f"Execute {tool_name}",
                reason="Action is allowlisted as safe for autonomous execution.",
            )

        # Default fallback: any unrecognized tool is blocked or requires approval
        return PolicyDecision(
            allowed=True,
            requires_approval=True,
            action_summary=f"Unknown tool execution: {tool_name}",
            reason="Unrecognized tool requires explicit verification before execution.",
        )

    @staticmethod
    def _format_action_summary(tool_name: str, args: Dict[str, Any]) -> str:
        """Format an informative summary of what the agent wants to do."""
        if tool_name == "delete_task":
            return f"Delete task with ID '{args.get('task_id', 'unknown')}'"
        elif tool_name == "send_email":
            return f"Send email to '{args.get('recipient')}' with subject '{args.get('subject')}'"
        elif tool_name == "create_calendar_event":
            return f"Create calendar event '{args.get('title')}' on {args.get('date')} at {args.get('time')}"
        elif tool_name == "delete_calendar_event":
            return f"Delete calendar meeting ID '{args.get('event_id')}'"
        elif tool_name == "wipe_memory":
            return "Wipe all semantic memories and preferences from database"
        elif tool_name == "desktop_run_command":
            return f"Execute Windows command: {args.get('command')}"
        return f"Perform sensitive operation: {tool_name}"

