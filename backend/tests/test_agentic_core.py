"""Integration tests for Phase 3: LLM & LangGraph Agentic Core with Approval Gates."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database.session import init_db
from app.agents.policy import PolicyEngine
from app.workflows.orchestrator import nexus_orchestrator
from app.workflows.state import AgentState


@pytest.fixture(autouse=True)
async def setup_database():
    """Ensure database tables are initialized before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_policy_engine_rules():
    """Verify deterministic policy evaluates safe vs sensitive tools correctly."""
    # Safe read tool
    safe_dec = PolicyEngine.evaluate("list_tasks", {})
    assert safe_dec.allowed is True
    assert safe_dec.requires_approval is False

    # Safe create tool
    create_dec = PolicyEngine.evaluate("create_task", {"title": "Write unit tests"})
    assert create_dec.allowed is True
    assert create_dec.requires_approval is False

    # Sensitive destructive tool
    delete_dec = PolicyEngine.evaluate("delete_task", {"task_id": "task-123"})
    assert delete_dec.allowed is True
    assert delete_dec.requires_approval is True
    assert "Delete task" in delete_dec.action_summary

    # Prohibited tool
    bad_dec = PolicyEngine.evaluate("arbitrary_shell_exec", {})
    assert bad_dec.allowed is False
    assert bad_dec.requires_approval is False


@pytest.mark.asyncio
async def test_langgraph_safe_tool_run():
    """Test text request running through LangGraph, executing a safe tool autonomously."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/chat",
            json={"message": "Show all my tasks"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["workflow_status"] == "completed"
        assert data["approval_required"] is False
        assert len(data["tool_results"]) > 0
        assert data["tool_results"][0]["tool"] == "list_tasks"
        assert len(data["final_response"]) > 0


@pytest.mark.asyncio
async def test_langgraph_create_task_tool():
    """Test creating a task through the agentic orchestrator."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/chat",
            json={"message": "create task Finalize Phase 3 Agentic Core"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["workflow_status"] == "completed"
        assert data["approval_required"] is False
        assert len(data["tool_results"]) > 0
        assert data["tool_results"][0]["tool"] == "create_task"
        assert "created successfully" in data["final_response"]


@pytest.mark.asyncio
async def test_langgraph_pauses_for_sensitive_approval():
    """Test graph execution pausing at approval gate when sensitive action is proposed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request deletion of a task (sensitive!)
        res = await client.post(
            "/api/v1/chat",
            json={"message": "delete task task-sample-1"},
        )
        assert res.status_code == 200
        data = res.json()

        # Exit criteria verification: graph paused for approval!
        assert data["approval_required"] is True
        assert data["approval_status"] == "pending"
        assert data["workflow_status"] == "pending_approval"
        assert data["approval_payload"] is not None
        assert data["approval_payload"]["tool_name"] == "delete_task"
        assert "Confirmation Required" in data["final_response"]

        # Tool was NOT executed yet
        assert len(data["tool_results"]) == 0


@pytest.mark.asyncio
async def test_approval_decision_resolution():
    """Test approving a pending action and verifying deferred execution."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger approval gate
        chat_res = await client.post(
            "/api/v1/chat",
            json={"message": "delete task task-sample-2"},
        )
        assert chat_res.status_code == 200
        assert chat_res.json()["approval_required"] is True

        # 2. Retrieve pending approvals
        appr_list_res = await client.get("/api/v1/approvals?status_filter=pending")
        assert appr_list_res.status_code == 200
        approvals = appr_list_res.json()
        assert len(approvals) > 0

        target_approval = approvals[0]
        approval_id = target_approval["id"]

        # 3. Grant approval
        decision_res = await client.post(
            f"/api/v1/approvals/{approval_id}/decision",
            json={"decision": "approved", "reason": "Authorized by user"},
        )
        assert decision_res.status_code == 200
        dec_data = decision_res.json()
        assert dec_data["status"] == "approved"
        assert dec_data["execution_result"]["success"] is True
        assert "successfully executed" in dec_data["message"]

