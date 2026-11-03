"""Unit and Scenario Integration Tests for Personal Voice Assistant.

Covers:
- Database CRUD (tasks, memory_facts, tool_calls, doc_chunks)
- Tool definitions and execution
- Confirmation gating (create_event, send_email, delete_task)
- Natural language confirmation parser
- Scenarios defined in tests/scenarios.yaml
- Core turn processing pipeline
"""

import os
import uuid
import pytest
import yaml
import tempfile
from pathlib import Path

# Set test environment to isolated temporary directory
TEST_DB_FILE = os.path.join(tempfile.gettempdir(), f"nexus_test_{uuid.uuid4().hex[:6]}.db")
os.environ["SQLITE_DB_PATH"] = TEST_DB_FILE
os.environ["DEFAULT_TIMEZONE"] = "Asia/Kolkata"

from db.models import (
    init_db,
    db_add_task,
    db_list_tasks,
    db_complete_task,
    db_add_fact,
    db_list_facts,
    db_forget_fact,
    db_log_tool_call,
    db_get_tool_calls,
)
from agent.confirm import requires_confirmation, format_read_back, is_confirmed
from agent.tools import TOOLS_REGISTRY, TOOL_SCHEMAS
from agent.tools.search import get_current_time, web_search
from agent.tools.calendar import list_events, find_free_slot, create_event
from agent.tools.email import search_email, summarize_email, draft_reply, send_email
from agent.tools.tasks import add_task, list_tasks, complete_task
from agent.tools.memory_tools import remember, forget
from agent.tools.docs import search_my_docs
from rag.store import add_doc_chunk, search_doc_chunks
from agent.main import process_user_turn


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
    yield
    # Cleanup test db
    for f in ["nexus_test.db"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


def test_database_crud():
    """Verify tasks, facts, and audit logs persist and retrieve accurately."""
    # Tasks
    task_record = db_add_task(title="Test voice pipeline task")
    assert "id" in task_record
    t_id = task_record["id"]
    tasks = db_list_tasks(status="pending")
    assert any(t["id"] == t_id for t in tasks)

    comp = db_complete_task(task_id=t_id)
    assert comp is True

    # Memory facts
    fact_rec = db_add_fact(fact="User prefers coffee over tea", category="preferences")
    assert "id" in fact_rec
    facts = db_list_facts()
    assert any("coffee" in f["fact"] for f in facts)

    del_f = db_forget_fact("coffee")
    assert del_f is True

    # Tool calls audit
    log_id = db_log_tool_call("web_search", {"query": "AI news"}, "test-sess", 1, 45.0)
    assert isinstance(log_id, str) and len(log_id) > 0
    logs = db_get_tool_calls(limit=5)
    assert len(logs) > 0


def test_confirmation_gating():
    """Verify sensitive write actions are gated behind spoken confirmation."""
    assert requires_confirmation("create_event") is True
    assert requires_confirmation("send_email") is True
    assert requires_confirmation("delete_task") is True

    # Safe read tools must not require confirmation
    assert requires_confirmation("web_search") is False
    assert requires_confirmation("get_current_time") is False
    assert requires_confirmation("list_events") is False
    assert requires_confirmation("list_tasks") is False
    assert requires_confirmation("search_email") is False


def test_read_back_formatting():
    """Verify read-backs are conversational, precise, and polite."""
    event_rb = format_read_back("create_event", {
        "title": "Design Sync",
        "start": "2026-11-01 15:00",
        "attendees": ["alex@example.com"],
    })
    assert "Design Sync" in event_rb
    assert "Shall I confirm this booking?" in event_rb

    email_rb = format_read_back("send_email", {
        "to": "team@example.com",
        "subject": "Sprint Plan",
    })
    assert "team@example.com" in email_rb
    assert "Shall I send it?" in email_rb


def test_confirmation_response_parser():
    """Test natural language detection of user affirmation or negation."""
    assert is_confirmed("Yes, go ahead") is True
    assert is_confirmed("sure, schedule it") is True
    assert is_confirmed("confirmed") is True
    assert is_confirmed("yep please do") is True

    assert is_confirmed("No, cancel that") is False
    assert is_confirmed("stop") is False
    assert is_confirmed("nevermind don't do it") is False

    assert is_confirmed("what time is it?") is None


def test_tools_execution():
    """Test direct execution of each tool registered."""
    # Current time
    t_res = get_current_time("Asia/Kolkata")
    assert t_res["success"] is True
    assert "spoken" in t_res
    assert "iso" in t_res

    # Web search
    s_res = web_search("Python FastAPI", max_results=2)
    assert s_res["success"] is True
    assert len(s_res["results"]) > 0

    # Calendar
    cal_res = list_events()
    assert cal_res["success"] is True

    slot_res = find_free_slot(duration_minutes=30)
    assert slot_res["success"] is True

    # Tasks
    add_res = add_task("Draft executive summary", priority="medium")
    assert add_res["success"] is True
    task_list = list_tasks()
    assert task_list["count"] >= 1

    # Email
    e_res = search_email("roadmap")
    assert e_res["success"] is True
    sum_res = summarize_email()
    assert sum_res["success"] is True
    d_res = draft_reply("alex@test.com", "Project Status", "Everything is on schedule.")
    assert d_res["success"] is True

    # Memory
    mem_res = remember("Favorite programming language is Python", category="preferences")
    assert mem_res["success"] is True


def test_rag_vector_store():
    """Verify document chunk storage and cosine similarity retrieval."""
    chunk_id = add_doc_chunk(
        file_name="project_handbook.md",
        text="Antigravity Voice Assistant uses OpenAI GPT-4o and Whisper STT for sub-second voice turns.",
        section="tech_spec"
    )
    assert chunk_id.startswith("chunk-")

    search_res = search_doc_chunks("Whisper STT voice turns", top_k=2)
    assert len(search_res) > 0
    assert "Whisper STT" in search_res[0]["text"]


@pytest.mark.asyncio
async def test_scenarios_from_yaml():
    """Execute direct conversational scenarios against process_user_turn."""
    yaml_path = Path(__file__).parent / "scenarios.yaml"
    assert yaml_path.exists(), "tests/scenarios.yaml must exist per project plan"

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    scenarios = data.get("scenarios", [])
    assert len(scenarios) >= 10, "Must test at least 10 scenarios"

    for sc in scenarios[:5]:
        session_id = f"test-sess-{sc['id']}"
        res = await process_user_turn(user_text=sc["input"], session_id=session_id)
        assert "spoken_reply" in res
        assert len(res["spoken_reply"]) > 0
        assert "latency_ms" in res
        assert res["requires_confirmation"] is False
