"""Specialist Desktop Agent enforcing allowlists and policy approval gates."""

from typing import Any, Dict, Optional
from app.agents.policy import PolicyEngine
from app.services.desktop_manager import desktop_manager, ALLOWED_APPLICATIONS


class DesktopAgent:
    """Specialist agent mediating Windows desktop companion commands."""

    @staticmethod
    def get_companion_status() -> Dict[str, Any]:
        """Return status and allowlists of the Windows desktop companion."""
        return desktop_manager.get_status()

    @staticmethod
    async def execute_desktop_action(
        action_name: str,
        params: Optional[Dict[str, Any]] = None,
        approval_granted: bool = False,
    ) -> Dict[str, Any]:
        """Execute a desktop command through the policy engine."""
        params = params or {}

        # 1. Evaluate with deterministic policy engine
        tool_name = action_name if action_name in [
            "get_desktop_status",
            "get_active_window",
            "get_system_metrics",
            "search_files",
        ] else "desktop_run_command"
        decision = PolicyEngine.evaluate(tool_name, {"action": action_name, **params})

        if not decision.allowed:
            return {
                "success": False,
                "error": f"Action '{action_name}' is prohibited by safety policy: {decision.reason}",
                "policy_blocked": True,
            }

        if decision.requires_approval and not approval_granted:
            return {
                "success": False,
                "approval_required": True,
                "action_summary": decision.action_summary,
                "reason": decision.reason,
                "message": f"Desktop action '{action_name}' requires explicit human approval before execution.",
            }

        # 2. Dispatch via companion manager
        result = await desktop_manager.dispatch_command(command_type=action_name, params=params)
        return result
