"""LangGraph agent state schema for Nexus Assistant."""

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """Explicit state representation across all LangGraph orchestration nodes."""

    # Identifiers
    user_id: Optional[str]
    conversation_id: Optional[str]
    request_id: str

    # User input and normalization
    user_message: str
    normalized_intent: Optional[str]
    conversation_history: List[Dict[str, str]]

    # Planning and routing
    plan: Optional[Dict[str, Any]]
    current_agent: Optional[str]

    # Tool calls and results
    pending_tool_calls: List[Dict[str, Any]]
    current_tool_call: Optional[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]

    # Approval gating
    approval_required: bool
    approval_status: str  # "none", "pending", "approved", "rejected"
    approval_id: Optional[str]
    approval_payload: Optional[Dict[str, Any]]
    approval_decision_reason: Optional[str]

    # Status and final response
    workflow_status: str  # "running", "pending_approval", "completed", "failed"
    error_details: Optional[str]
    final_response: Optional[str]

