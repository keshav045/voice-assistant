"""Regression test suite verifying fixes across HITL gating, security, RAG, voice, and tools."""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent.confirm import is_confirmed
from agent.main import app, _clean_spoken_text, process_user_turn
from agent.screening import screen_input, screen_output
from agent.tools.calc import calculator
from agent.tools.calendar import create_event, find_free_slot
from agent.tools.launcher import open_app
from agent.tools.medical import medical_search
from agent.voice import clean_spoken_text
from db.models import (
    db_add_task,
    db_create_user,
    db_delete_user_oauth,
    db_get_user_oauth,
    db_list_calendar_events,
    db_list_tasks,
    db_save_user_oauth,
    get_db_connection,
)
from rag.ingest import chunk_text
from rag.store import search_doc_chunks


@pytest.mark.asyncio
async def test_hitl_confirmation_stages_before_mutation_and_resumes():
    """create_event and delete_task must NOT mutate DB before confirmation and must mutate only after yes."""
    uid = f"hitl-user-{uuid.uuid4().hex[:6]}"
    sess = f"hitl-sess-{uuid.uuid4().hex[:6]}"
    task = db_add_task(title="Delete me after confirmation", user_id=uid)

    client = TestClient(app)

    # 1. Stage delete_task via turn (LLM/fallback path)
    with patch("agent.main._run_openai_tool_loop") as mock_loop:
        # Simulate direct dispatch fallback by temporarily testing staged helper through process_user_turn fallback
        from agent.main import _stage_or_execute_tool

        res, req_conf = await _stage_or_execute_tool("delete_task", {"task_id": task["id"]}, sess, uid, f"delete task {task['id']}")
        assert req_conf is True
        assert res["success"] is True
        # DB must still contain the task BEFORE confirmation!
        assert any(t["id"] == task["id"] for t in db_list_tasks(user_id=uid))

    # 2. Confirm via /api/chat/confirm -> must execute delete ONCE
    conf_res = client.post("/api/chat/confirm", json={"session_id": sess, "approved": True, "user_id": uid})
    assert conf_res.status_code == 200
    assert conf_res.json()["status"] == "success"
    assert not any(t["id"] == task["id"] for t in db_list_tasks(user_id=uid))

    # 3. Verify cancel does not create calendar event
    sess_cal = f"hitl-cal-{uuid.uuid4().hex[:6]}"
    before_count = len(db_list_calendar_events(user_id=uid))
    from agent.main import _stage_or_execute_tool
    ev_res, ev_req = await _stage_or_execute_tool(
        "create_event",
        {"title": "Unconfirmed Sync", "start": "tomorrow 4 PM", "end": "tomorrow 5 PM"},
        sess_cal,
        uid,
        "schedule meeting Unconfirmed Sync tomorrow from 4 to 5 PM",
    )
    assert ev_req is True
    assert ev_res["success"] is True
    assert len(db_list_calendar_events(user_id=uid)) == before_count

    cancel_turn = await process_user_turn("no, cancel that", session_id=sess_cal, user_id=uid)
    assert "cancel" in cancel_turn["spoken_reply"].lower()
    assert len(db_list_calendar_events(user_id=uid)) == before_count


def test_oauth_isolation_and_no_cross_user_wipe():
    """Anonymous requests must never inherit guest OAuth, and user logout/disconnect must not wipe other users."""
    alice = db_create_user(f"alice_{uuid.uuid4().hex[:6]}", "Password!123")
    bob = db_create_user(f"bob_{uuid.uuid4().hex[:6]}", "Password!123")
    assert alice and bob

    db_save_user_oauth(user_id=alice["id"], email="alice@gmail.com", access_token="tok_a", refresh_token="ref_a")
    db_save_user_oauth(user_id="guest", email="guest_leak_check@gmail.com", access_token="tok_g", refresh_token="ref_g")

    client = TestClient(app)
    me_anon = client.get("/api/auth/me").json()
    assert me_anon["authenticated"] is False
    assert "token" not in me_anon

    # Bob has no OAuth; deleting Bob's OAuth must NOT wipe Alice's or guest's OAuth!
    assert db_delete_user_oauth(user_id=bob["id"], provider="google") is False
    alice_rec = db_get_user_oauth(user_id=alice["id"], provider="google")
    assert alice_rec is not None and alice_rec["email"] == "alice@gmail.com"
    assert db_get_user_oauth(user_id=bob["id"], provider="google") is None

    db_delete_user_oauth(user_id=alice["id"], provider="google")
    db_delete_user_oauth(user_id="guest", provider="google")


def test_google_oauth_callback_escapes_xss():
    """OAuth error query params must be HTML-escaped to prevent reflected XSS."""
    client = TestClient(app)
    payload = "<script>alert('xss')</script>"
    resp = client.get(f"/api/auth/google/callback?error={payload}")
    assert resp.status_code == 200
    assert "<script>alert" not in resp.text
    assert "&lt;script&gt;alert" in resp.text


def test_voice_cleaners_and_confirmation_parser_boundaries():
    """Voice text sanitization and confirmation parser must preserve math/identifiers and respect word boundaries."""
    math_spoken = clean_spoken_text("2 + 2 = 4 and 50% of $100 is 50")
    assert "+" in math_spoken and "=" in math_spoken and "%" in math_spoken and "$" in math_spoken

    ident_spoken = _clean_spoken_text("Use function `compute_total` or var snake_case_val")
    assert "snake_case_val" in ident_spoken

    assert is_confirmed("I notice a typo") is None
    assert is_confirmed("awaiting confirmation") is None
    assert is_confirmed("Yes, no problem") is True
    assert is_confirmed("No, stop please") is False


def test_tool_edge_fixes():
    """Verify calculator discounts, calendar slot durations/ordering, medical matching, launcher, and RAG fixes."""
    # Calc discount
    disc = calculator("20% off 500")
    assert disc["success"] is True and disc["result"] == 400.0

    # Calendar inverted range and real duration slot calculation
    bad_evt = create_event("Invalid Meeting", "6 PM", "4 PM")
    assert bad_evt["success"] is False

    slot_120 = find_free_slot(duration_minutes=120, window="tomorrow")
    assert slot_120["success"] is True
    s_h, s_m = map(int, slot_120["slot"]["start"].split(":"))
    e_h, e_m = map(int, slot_120["slot"]["end"].split(":"))
    assert (e_h * 60 + e_m) - (s_h * 60 + s_m) == 120

    # Medical: Pan 40 must resolve to Pantoprazole, not Paracetamol/Panadol
    med_pan = medical_search("Pan 40", topic="uses")
    assert med_pan["success"] is True
    assert "pantoprazole" in med_pan["generic_name"].lower()

    # Launcher: 'app' must not falsely open WhatsApp
    with patch("webbrowser.open_new_tab"):
        bad_app = open_app("app")
        assert bad_app["success"] is False

    # RAG chunk guard when overlap >= chunk_size and mixed embedding dim tolerance
    chunks = chunk_text("alpha beta gamma delta epsilon", chunk_size=3, overlap=5)
    assert len(chunks) >= 2

    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO doc_chunks (id, user_id, file, section, text, embedding, modified_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("chunk-mixeddim", "guest", "test.txt", "sec", "Quarterly budget forecast report", "[0.1, 0.2, 0.3]", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
    try:
        hits = search_doc_chunks("budget forecast", top_k=2)
        assert any(h["id"] == "chunk-mixeddim" and h["score"] > 0 for h in hits)
    finally:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM doc_chunks WHERE id = 'chunk-mixeddim'")
            conn.commit()


def test_livekit_speech_launch_and_screening_guards():
    """LiveKit app auto-launch must ignore questions/substrings and screening must catch physical/wire commands."""
    from agent.livekit_worker import _maybe_launch_app_from_speech

    with patch("agent.tools.launcher.open_app") as mock_open:
        assert _maybe_launch_app_from_speech("Who founded YouTube?") is False
        assert _maybe_launch_app_from_speech("I am calculating my taxes right now") is False
        mock_open.assert_not_called()

    assert not screen_input("Please physically turn off my kitchen microwave right now.").passed
    assert not screen_input("Wire $5,000 to my offshore account").passed
    assert "[REDACTED_API_KEY]" in screen_output("Key is sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456").sanitized_text

    # WhatsApp remap & placeholder contact_name extraction (T026)
    from types import SimpleNamespace
    from agent.main import _remap_and_execute_preparation

    tc_wa = SimpleNamespace(function=SimpleNamespace(name="send_whatsapp_message", arguments='{"contact_name": "Contact"}'))
    r_name, r_args = _remap_and_execute_preparation(tc_wa, "Open WhatsApp chat with Rahul")
    assert r_name == "send_whatsapp_message"
    assert r_args["contact_name"] == "Rahul"

    tc_open_wa = SimpleNamespace(function=SimpleNamespace(name="open_app", arguments='{"name": "whatsapp"}'))
    r_name2, r_args2 = _remap_and_execute_preparation(tc_open_wa, "Open WhatsApp chat with Rahul")
    assert r_name2 == "send_whatsapp_message"
    assert r_args2["contact_name"] == "Rahul"

    tc_just_open = SimpleNamespace(function=SimpleNamespace(name="send_whatsapp_message", arguments='{"contact_name": ""}'))
    r_name3, r_args3 = _remap_and_execute_preparation(tc_just_open, "Open WhatsApp")
    assert r_name3 == "open_app"
    assert r_args3["name"] == "whatsapp"

    tc_py_search = SimpleNamespace(function=SimpleNamespace(name="run_python_code", arguments='{"code": "print(dir())"}'))
    r_name4, r_args4 = _remap_and_execute_preparation(tc_py_search, "Search for Python 3.13 features, give me 3 results")
    assert r_name4 == "web_search"
    assert r_args4["query"] == "Python 3.13 features"
    assert r_args4["max_results"] == 3
