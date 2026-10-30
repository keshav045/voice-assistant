"""Chat endpoint executing the LangGraph orchestrator."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.models.agent import AgentRun, ApprovalRequest, ToolExecution
from app.workflows.orchestrator import nexus_orchestrator
from app.workflows.state import AgentState

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None


class ChatResponse(BaseModel):
    request_id: str
    user_message: str
    normalized_intent: Optional[str]
    plan: Optional[Dict[str, Any]]
    current_agent: Optional[str]
    tool_results: List[Dict[str, Any]]
    approval_required: bool
    approval_status: str
    approval_payload: Optional[Dict[str, Any]]
    workflow_status: str
    final_response: str


@router.post("", response_model=ChatResponse)
async def submit_chat_message(
    chat_in: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Submit a user request to the LangGraph agent orchestrator."""
    request_id = f"req-{uuid.uuid4().hex[:12]}"

    # Initial Agent State
    initial_state: AgentState = {
        "request_id": request_id,
        "user_message": chat_in.message,
        "conversation_id": str(chat_in.conversation_id) if chat_in.conversation_id else None,
        "user_id": str(chat_in.user_id) if chat_in.user_id else None,
        "conversation_history": [],
        "tool_results": [],
        "approval_required": False,
        "approval_status": "none",
        "workflow_status": "running",
    }

    # Run LangGraph Orchestrator
    try:
        final_state = await nexus_orchestrator.ainvoke(initial_state)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Orchestration error: {str(e)}",
        )

    # Persist AgentRun record in database
    agent_run = AgentRun(
        request_id=request_id,
        user_message=chat_in.message,
        conversation_id=chat_in.conversation_id,
        user_id=chat_in.user_id,
        normalized_intent=final_state.get("normalized_intent"),
        plan=final_state.get("plan"),
        workflow_status=final_state.get("workflow_status", "completed"),
        final_response=final_state.get("final_response"),
    )
    db.add(agent_run)
    await db.commit()
    await db.refresh(agent_run)

    # Persist any tool executions to audit log
    for res in final_state.get("tool_results", []):
        output = res.get("output", {})
        tool_exec = ToolExecution(
            agent_run_id=agent_run.id,
            tool_name=res.get("tool", "unknown"),
            tool_input=res.get("args", {}),
            tool_output=output.get("result", {}),
            status="success" if output.get("success") else "failed",
            latency_ms=output.get("latency_ms", 0.0),
            error_message=output.get("error"),
        )
        db.add(tool_exec)

    # Persist approval request if graph paused at approval gate
    if final_state.get("approval_required"):
        payload = final_state.get("approval_payload") or {}
        approval = ApprovalRequest(
            agent_run_id=agent_run.id,
            tool_name=payload.get("tool_name", "unknown"),
            action_summary=payload.get("action_summary", "Approval required"),
            tool_payload=payload.get("tool_payload", {}),
            status="pending",
        )
        db.add(approval)

    await db.commit()

    return ChatResponse(
        request_id=request_id,
        user_message=chat_in.message,
        normalized_intent=final_state.get("normalized_intent"),
        plan=final_state.get("plan"),
        current_agent=final_state.get("current_agent"),
        tool_results=final_state.get("tool_results", []),
        approval_required=final_state.get("approval_required", False),
        approval_status=final_state.get("approval_status", "none"),
        approval_payload=final_state.get("approval_payload"),
        workflow_status=final_state.get("workflow_status", "completed"),
        final_response=final_state.get("final_response", "Request processed."),
    )
