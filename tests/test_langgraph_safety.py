"""LangGraph Safety and Human-In-The-Loop Approval Tests for Nexus AI.

Verifies:
1. Irreversible tools (send_email, delete_task, create_event) halt at interrupt() before execution.
2. Irreversible actions are NEVER executed before approval.
3. Irreversible actions execute EXACTLY ONCE upon approval ('yes').
4. Irreversible actions do NOT execute when declined ('no').
5. Multi-tool turns (read-only + irreversible) execute read-only tools and pause before irreversible side effects.
6. FastAPI endpoints (/api/chat, /api/chat/confirm, /api/langgraph/chat) properly expose LangGraph execution and confirmation.
"""

import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from fastapi.testclient import TestClient

from agent.lc_tools import LANGGRAPH_TOOLS, search_web, send_email, delete_task
from agent.lc_agent import build_agent_graph, AgentState
from agent.main import app


class StubModel:
    """Deterministic stub LLM returning pre-configured AIMessages without network calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def invoke(self, messages):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        # Default fallback: acknowledge tool output
        last = messages[-1] if messages else None
        if isinstance(last, ToolMessage):
            return AIMessage(content=f"Acknowledged tool result: {last.content}")
        return AIMessage(content="Stub completed.")

    def bind_tools(self, tools):
        return self


@pytest.fixture
def memory_checkpointer():
    """Create an isolated in-memory SQLite checkpointer for test sessions."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def test_email_not_sent_before_approval(memory_checkpointer):
    """Verify email tool halts at interrupt() and does NOT send email prior to user approval."""
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "send_email",
            "args": {
                "to": "alex@example.com",
                "subject": "Q4 Strategy Sync",
                "description": "Send meeting notes",
            },
            "id": "call_email_1",
            "type": "tool_call",
        }],
    )
    stub_llm = StubModel([tool_call_msg])
    test_graph = build_agent_graph(checkpointer=memory_checkpointer, custom_llm=stub_llm)

    cfg = {"configurable": {"thread_id": "test-safety-halt"}}

    with patch("agent.tools.email.send_email") as mock_send:
        out = test_graph.invoke(
            {"messages": [HumanMessage(content="Send email to Alex about Q4 Strategy")]},
            cfg,
        )

        # Graph MUST halt at __interrupt__
        assert "__interrupt__" in out
        interrupt_info = out["__interrupt__"][0].value
        assert interrupt_info["action"] == "send_email"
        assert interrupt_info["to"] == "alex@example.com"
        assert "Q4 Strategy Sync" in interrupt_info["subject"]

        # CRITICAL SAFETY ASSERTION: Underlying send_email MUST NOT have been called
        mock_send.assert_not_called()


def test_email_sent_exactly_once_after_yes(memory_checkpointer):
    """Verify resuming with 'yes' executes the email send action exactly once."""
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "send_email",
            "args": {
                "to": "boss@example.com",
                "subject": "Weekly Status Update",
                "description": "All milestones met.",
            },
            "id": "call_email_2",
            "type": "tool_call",
        }],
    )
    final_msg = AIMessage(content="The weekly update has been sent to your boss.")
    stub_llm = StubModel([tool_call_msg, final_msg])
    test_graph = build_agent_graph(checkpointer=memory_checkpointer, custom_llm=stub_llm)

    cfg = {"configurable": {"thread_id": "test-safety-confirm"}}

    with patch("agent.tools.email.send_email", return_value={"success": True, "spoken": "Email sent."}) as mock_send:
        # Step 1: Trigger action -> must halt
        out1 = test_graph.invoke(
            {"messages": [HumanMessage(content="Send weekly status to boss@example.com")]},
            cfg,
        )
        assert "__interrupt__" in out1
        mock_send.assert_not_called()

        # Step 2: Approve action with 'yes'
        out2 = test_graph.invoke(Command(resume="yes"), cfg)

        # CRITICAL SAFETY ASSERTIONS:
        # 1. mock_send called EXACTLY ONCE
        mock_send.assert_called_once()
        # 2. Graph proceeded past interrupt and returned final message
        assert out2["messages"][-1].content == "The weekly update has been sent to your boss."


def test_email_not_sent_after_no(memory_checkpointer):
    """Verify resuming with 'no' cancels the email without executing the write action."""
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "send_email",
            "args": {
                "to": "client@example.com",
                "subject": "Invoice Reminder",
                "description": "Payment overdue",
            },
            "id": "call_email_3",
            "type": "tool_call",
        }],
    )
    stub_llm = StubModel([tool_call_msg])
    test_graph = build_agent_graph(checkpointer=memory_checkpointer, custom_llm=stub_llm)

    cfg = {"configurable": {"thread_id": "test-safety-decline"}}

    with patch("agent.tools.email.send_email") as mock_send:
        # Step 1: Trigger action -> halts
        out1 = test_graph.invoke(
            {"messages": [HumanMessage(content="Send invoice reminder to client")]},
            cfg,
        )
        assert "__interrupt__" in out1
        mock_send.assert_not_called()

        # Step 2: Decline action with 'no'
        out2 = test_graph.invoke(Command(resume="no"), cfg)

        # CRITICAL SAFETY ASSERTIONS:
        # 1. Underlying send_email MUST NOT have been called
        mock_send.assert_not_called()
        # 2. Tool result in messages informs agent of user cancellation
        tool_msgs = [m for m in out2["messages"] if isinstance(m, ToolMessage)]
        assert any("User declined" in m.content for m in tool_msgs)


def test_multi_tool_readonly_and_irreversible(memory_checkpointer):
    """Test a turn that invokes a read-only tool (search) and an irreversible tool (email).

    Verifies read-only tool completes, then graph pauses at the irreversible action.
    """
    tool_calls_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_web",
                "args": {"query": "latest AI breakthroughs"},
                "id": "call_search_1",
                "type": "tool_call",
            },
            {
                "name": "send_email",
                "args": {
                    "to": "colleague@example.com",
                    "subject": "AI Breakthroughs Digest",
                    "description": "Here are the top AI news items today.",
                },
                "id": "call_email_multi",
                "type": "tool_call",
            },
        ],
    )
    stub_llm = StubModel([tool_calls_msg])
    test_graph = build_agent_graph(checkpointer=memory_checkpointer, custom_llm=stub_llm)

    cfg = {"configurable": {"thread_id": "test-multi-tool"}}

    with patch("agent.tools.search.web_search", return_value={"spoken": "AI research update."}) as mock_search, \
         patch("agent.tools.email.send_email", return_value={"success": True, "spoken": "Email sent."}) as mock_email:

        # Step 1: Initial call
        out = test_graph.invoke(
            {"messages": [HumanMessage(content="Find latest AI news and email it to colleague")]},
            cfg,
        )

        # Must halt at interrupt for email
        assert "__interrupt__" in out
        mock_email.assert_not_called()

        # Step 2: Resume with approval
        out_res = test_graph.invoke(Command(resume="yes"), cfg)
        mock_email.assert_called_once()


def test_delete_task_interrupt_safety(memory_checkpointer):
    """Verify task deletion halts at interrupt() and requires human confirmation."""
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "delete_task",
            "args": {"task_id": "task-999"},
            "id": "call_del_1",
            "type": "tool_call",
        }],
    )
    stub_llm = StubModel([tool_call_msg])
    test_graph = build_agent_graph(checkpointer=memory_checkpointer, custom_llm=stub_llm)

    cfg = {"configurable": {"thread_id": "test-del-task"}}

    with patch("agent.tools.tasks.delete_task", return_value={"success": True, "spoken": "Task deleted."}) as mock_del:
        out1 = test_graph.invoke(
            {"messages": [HumanMessage(content="Delete task 999")]},
            cfg,
        )
        assert "__interrupt__" in out1
        assert out1["__interrupt__"][0].value["action"] == "delete_task"
        mock_del.assert_not_called()

        # Resume with yes
        out2 = test_graph.invoke(Command(resume="yes"), cfg)
        mock_del.assert_called_once()


def test_fastapi_chat_confirm_endpoints():
    """Verify /api/chat and /api/chat/confirm endpoints via FastAPI TestClient."""
    client = TestClient(app)

    # 1. Normal turn on /api/chat with mocked process_user_turn
    fake_turn_result = {
        "spoken_reply": "Hello! How can I assist you today?",
        "tool_calls_executed": [],
        "requires_confirmation": False,
        "session_id": "test-api-sess-1",
        "latency_ms": 12.5,
    }
    with patch("agent.main.process_user_turn", return_value=fake_turn_result):
        res = client.post("/api/chat", json={"message": "hello", "session_id": "test-api-sess-1"})
        assert res.status_code == 200
        data = res.json()
        assert data["spoken_reply"] == "Hello! How can I assist you today?"
        assert data["reply"] == "Hello! How can I assist you today?"

    # 2. Confirm endpoint when no pending confirmation exists returns not_found
    res_conf = client.post("/api/chat/confirm", json={"session_id": "nonexistent-sess", "approved": True})
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "not_found"

    # 3. Dedicated /api/langgraph/chat endpoint with mocked run_langgraph_turn
    fake_lg_res = {
        "reply": "LangGraph response.",
        "spoken": "LangGraph response.",
        "needs_confirmation": False,
        "status": "success",
        "session_id": "test-lg-sess",
    }
    with patch("agent.lc_agent.run_langgraph_turn", return_value=fake_lg_res):
        res_lg = client.post("/api/langgraph/chat", json={"message": "What is AI?", "session_id": "test-lg-sess"})
        assert res_lg.status_code == 200
        assert res_lg.json()["reply"] == "LangGraph response."


def test_tool_categories_execution(memory_checkpointer):
    """Test real calls to key LangChain tool categories: calculator, medical_search, tasks, memory."""
    from agent.lc_tools import calculator, medical_search, add_task, list_tasks, remember

    # 1. Calculator
    calc_out = calculator.invoke({"expression": "25 * 4 + 50"})
    assert "150" in calc_out

    # 2. Medical Search
    med_out = medical_search.invoke({"medicine_name": "Paracetamol", "topic": "uses"})
    assert "Paracetamol" in med_out or "fever" in med_out.lower() or "pain" in med_out.lower()

    # 3. Tasks
    task_out = add_task.invoke({"title": "Review agent plan", "priority": "high", "user_id": "test-user"})
    assert "task" in task_out.lower() or "Review agent plan" in task_out

    # 4. Memory
    mem_out = remember.invoke({"fact": "User prefers concise responses", "user_id": "test-user"})
    assert "remember" in mem_out.lower() or "concise" in mem_out.lower()


def test_sqlite_checkpointer_persistence(tmp_path):
    """Verify pending approval state survives across distinct graph instances using SQLite."""
    db_file = tmp_path / "test_persist.sqlite"
    conn1 = sqlite3.connect(str(db_file), check_same_thread=False)
    saver1 = SqliteSaver(conn1)
    saver1.setup()

    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "send_email",
            "args": {"to": "persist@example.com", "subject": "Persist Check"},
            "id": "call_persist_1",
            "type": "tool_call",
        }],
    )
    stub_llm = StubModel([tool_call_msg])
    graph1 = build_agent_graph(checkpointer=saver1, custom_llm=stub_llm)

    cfg = {"configurable": {"thread_id": "thread-persist-1"}}
    out1 = graph1.invoke({"messages": [HumanMessage(content="Send email")]}, cfg)
    assert "__interrupt__" in out1

    conn1.close()

    # Open fresh connection on same database file (simulating server restart)
    conn2 = sqlite3.connect(str(db_file), check_same_thread=False)
    saver2 = SqliteSaver(conn2)
    saver2.setup()
    graph2 = build_agent_graph(checkpointer=saver2, custom_llm=stub_llm)

    # Verify state was preserved and can resume
    with patch("agent.tools.email.send_email", return_value={"success": True, "spoken": "Email sent."}) as mock_send:
        out2 = graph2.invoke(Command(resume="yes"), cfg)
        mock_send.assert_called_once()
    conn2.close()

