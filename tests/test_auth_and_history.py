"""Unit tests for User Authentication and Personal Chat History."""

import pytest
import uuid
from db.models import (
    init_db,
    db_create_user,
    db_get_user_by_username,
    db_get_user_by_id,
    verify_password,
    db_create_session_token,
    db_get_user_from_token,
    db_delete_session_token,
    db_save_chat_turn,
    db_list_chat_history,
    db_clear_chat_history,
    db_delete_chat_turn,
)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


def test_user_registration_and_password_hashing():
    uname = f"user_{uuid.uuid4().hex[:6]}"
    user = db_create_user(username=uname, password="MySecurePassword!456", email=f"{uname}@example.com")
    assert user is not None
    assert user["username"] == uname
    assert "id" in user

    # Duplicate registration should return None
    dup = db_create_user(username=uname, password="AnotherPassword")
    assert dup is None

    # Fetch and verify password
    record = db_get_user_by_username(uname)
    assert record is not None
    assert verify_password("MySecurePassword!456", record["password_hash"]) is True
    assert verify_password("WrongPassword", record["password_hash"]) is False


def test_auth_token_sessions():
    uname = f"token_user_{uuid.uuid4().hex[:6]}"
    user = db_create_user(username=uname, password="TokenPassword99")
    assert user is not None

    token = db_create_session_token(user["id"])
    assert token is not None and len(token) > 20

    resolved_user = db_get_user_from_token(token)
    assert resolved_user is not None
    assert resolved_user["id"] == user["id"]
    assert resolved_user["username"] == uname

    # Delete token
    deleted = db_delete_session_token(token)
    assert deleted is True

    # Resolved should now be None
    assert db_get_user_from_token(token) is None


def test_chat_history_persistence():
    uname = f"hist_user_{uuid.uuid4().hex[:6]}"
    user = db_create_user(username=uname, password="Password12345")
    assert user is not None
    u_id = user["id"]
    s_id = "test-session-1"

    # Save turns
    t1_id = db_save_chat_turn(
        user_id=u_id,
        session_id=s_id,
        user_message="Hello assistant",
        spoken_reply="Hello! How can I help you?",
        tool_calls=[],
        latency_ms=120.0,
    )
    assert t1_id.startswith("hist-")

    t2_id = db_save_chat_turn(
        user_id=u_id,
        session_id=s_id,
        user_message="What is 10 plus 20?",
        spoken_reply="The answer is thirty.",
        tool_calls=[{"tool": "calculator", "args": {"expression": "10+20"}}],
        latency_ms=150.0,
    )
    assert t2_id.startswith("hist-")

    # List history
    history = db_list_chat_history(user_id=u_id)
    assert len(history) == 2
    # Most recent first
    assert history[0]["user_message"] == "What is 10 plus 20?"
    assert len(history[0]["tool_calls"]) == 1
    assert history[0]["tool_calls"][0]["tool"] == "calculator"

    # Delete single turn
    del_turn = db_delete_chat_turn(t2_id, u_id)
    assert del_turn is True
    history_after = db_list_chat_history(user_id=u_id)
    assert len(history_after) == 1
    assert history_after[0]["id"] == t1_id

    # Clear all history
    cleared = db_clear_chat_history(user_id=u_id)
    assert cleared is True
    assert len(db_list_chat_history(user_id=u_id)) == 0


def test_health_probes():
    from fastapi.testclient import TestClient
    from agent.main import app

    client = TestClient(app)
    r1 = client.get("/health")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["status"] == "healthy"
    assert d1["database"] == "ok"
    assert d1["service"] == "Nexus Personal Voice Assistant"

    r2 = client.get("/api/health")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["status"] == "healthy"
    assert d2["database"] == "ok"


def test_session_grouped_history_endpoints():
    from fastapi.testclient import TestClient
    from agent.main import app
    from db.models import db_save_chat_turn, db_list_chat_sessions, db_get_session_turns

    client = TestClient(app)
    uname = f"api_user_{uuid.uuid4().hex[:6]}"
    signup_res = client.post("/api/auth/signup", json={"username": uname, "password": "Password123!"})
    assert signup_res.status_code == 200
    token = signup_res.json()["token"]
    user_id = signup_res.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add turns under two distinct sessions
    s1 = f"session_alpha_{uuid.uuid4().hex[:4]}"
    s2 = f"session_beta_{uuid.uuid4().hex[:4]}"

    db_save_chat_turn(user_id=user_id, session_id=s1, user_message="First question in Alpha", spoken_reply="Answer Alpha 1")
    db_save_chat_turn(user_id=user_id, session_id=s1, user_message="Second question in Alpha", spoken_reply="Answer Alpha 2")
    db_save_chat_turn(user_id=user_id, session_id=s2, user_message="First question in Beta", spoken_reply="Answer Beta 1")

    # Verify GET /api/history returns sessions
    res_hist = client.get("/api/history", headers=headers)
    assert res_hist.status_code == 200
    data = res_hist.json()
    assert data["success"] is True
    sessions = data["sessions"]
    assert len(sessions) >= 2
    session_ids = [s["session_id"] for s in sessions]
    assert s1 in session_ids
    assert s2 in session_ids

    # Find s1 session summary
    s1_summary = next(s for s in sessions if s["session_id"] == s1)
    assert s1_summary["turn_count"] == 2
    assert s1_summary["title"] == "First question in Alpha"

    # Verify GET /api/history/{session_id} returns all turns in order
    res_s1 = client.get(f"/api/history/{s1}", headers=headers)
    assert res_s1.status_code == 200
    turns_data = res_s1.json()
    assert turns_data["count"] == 2
    assert turns_data["turns"][0]["user_message"] == "First question in Alpha"
    assert turns_data["turns"][1]["user_message"] == "Second question in Alpha"

    # Delete s1 session
    del_res = client.delete(f"/api/history/{s1}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify s1 is now gone from sessions
    res_after = client.get("/api/history", headers=headers)
    remaining_ids = [s["session_id"] for s in res_after.json()["sessions"]]
    assert s1 not in remaining_ids
    assert s2 in remaining_ids


def test_google_oauth_endpoints():
    from fastapi.testclient import TestClient
    from agent.main import app
    from db.models import db_save_user_oauth, db_get_user_oauth, db_delete_user_oauth

    client = TestClient(app)
    # 1. Unconfigured state
    res_url = client.get("/api/auth/google/url")
    assert res_url.status_code == 200
    assert "configured" in res_url.json()

    # 2. Status endpoint
    res_status = client.get("/api/auth/google/status")
    assert res_status.status_code == 200
    assert res_status.json()["connected"] is False

    # 3. Simulate connected state
    uid = f"usr_{uuid.uuid4().hex[:6]}"
    saved = db_save_user_oauth(
        user_id=uid,
        email="test_user@gmail.com",
        access_token="fake_access_token",
        refresh_token="fake_refresh_token",
    )
    assert saved["email"] == "test_user@gmail.com"

    rec = db_get_user_oauth(uid)
    assert rec is not None
    assert rec["email"] == "test_user@gmail.com"
    assert rec["refresh_token"] == "fake_refresh_token"

    # 4. Disconnect
    deleted = db_delete_user_oauth(uid)
    assert deleted is True
    assert db_get_user_oauth(uid) is None

