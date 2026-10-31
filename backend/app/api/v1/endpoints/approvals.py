"""Approval Gate REST endpoints for reviewing sensitive actions."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.tools.tool_registry import execute_tool_call
from app.database.session import get_db
from app.models.agent import ApprovalRequest, ToolExecution

router = APIRouter()


class ApprovalDecision(BaseModel):
    decision: str  # "approved" or "rejected"
    reason: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    agent_run_id: uuid.UUID
    tool_name: str
    action_summary: str
    tool_payload: Optional[Dict[str, Any]]
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None


@router.get("", response_model=List[ApprovalResponse])
async def list_approvals(
    status_filter: Optional[str] = "pending",
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List pending actions waiting for human approval."""
    stmt = select(ApprovalRequest)
    if status_filter:
        stmt = stmt.where(ApprovalRequest.status == status_filter)
    stmt = stmt.order_by(ApprovalRequest.created_at.desc())

    result = await db.execute(stmt)
    approvals = result.scalars().all()
    return approvals


@router.post("/{approval_id}/decision")
async def submit_approval_decision(
    approval_id: uuid.UUID,
    decision_in: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Approve or reject a sensitive tool action."""
    result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Approval has already been resolved with status: {approval.status}",
        )

    approval.status = decision_in.decision
    approval.decision_reason = decision_in.reason
    approval.decided_at = datetime.now(timezone.utc)

    execution_output = None

    # If approved, execute the sensitive tool call
    if decision_in.decision == "approved":
        tool_res = execute_tool_call(approval.tool_name, approval.tool_payload or {})
        execution_output = tool_res

        # Record ToolExecution
        tool_exec = ToolExecution(
            agent_run_id=approval.agent_run_id,
            tool_name=approval.tool_name,
            tool_input=approval.tool_payload or {},
            tool_output=tool_res.get("result", {}),
            status="success" if tool_res.get("success") else "failed",
            latency_ms=tool_res.get("latency_ms", 0.0),
            error_message=tool_res.get("error"),
        )
        db.add(tool_exec)

    await db.commit()
    await db.refresh(approval)

    return {
        "approval_id": str(approval.id),
        "status": approval.status,
        "tool_name": approval.tool_name,
        "execution_result": execution_output,
        "message": (
            f"Action '{approval.action_summary}' was successfully executed."
            if decision_in.decision == "approved"
            else f"Action '{approval.action_summary}' was rejected."
        ),
    }

