"""Integration tests for Phase 5: Gmail Integration & Email Assistant."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database.session import init_db
from app.agents.policy import PolicyEngine


@pytest.fixture(autouse=True)
async def setup_database():
    """Ensure database tables are initialized before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_search_emails():
    """Test searching Gmail inbox via API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Search all
        res = await client.get("/api/v1/emails/search")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["count"] >= 3

        # Search keyword
        res_kw = await client.get("/api/v1/emails/search?q=interview")
        assert res_kw.status_code == 200
        kw_data = res_kw.json()
        assert kw_data["success"] is True
        assert kw_data["count"] >= 1
        assert any("interview" in m["subject"].lower() for m in kw_data["messages"])


@pytest.mark.asyncio
async def test_summarize_emails():
    """Test email summarization API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/emails/summarize",
            json={"query": "interview"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["emails_analyzed"] >= 1
        assert len(data["summary"]) > 0


@pytest.mark.asyncio
async def test_create_and_list_drafts():
    """Test creating an email draft and listing drafts."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        draft_payload = {
            "recipient": "recruiter@apextechnologies.io",
            "subject": "Re: Interview Availability - Keshav",
            "body": "Thank you for the invitation. Tomorrow at 3:00 PM UTC works perfectly for me.",
        }
        create_res = await client.post("/api/v1/emails/drafts", json=draft_payload)
        assert create_res.status_code == 201
        created = create_res.json()
        assert created["recipient"] == draft_payload["recipient"]
        assert created["status"] == "draft"
        assert created["id"] is not None

        # List drafts
        list_res = await client.get("/api/v1/emails/drafts")
        assert list_res.status_code == 200
        drafts = list_res.json()
        assert len(drafts) >= 1
        assert any(d["id"] == created["id"] for d in drafts)


@pytest.mark.asyncio
async def test_send_email_and_update_draft():
    """Test sending an email and updating draft status to sent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create draft first
        draft_res = await client.post(
            "/api/v1/emails/drafts",
            json={
                "recipient": "lead-designer@nexus.ai",
                "subject": "Review approved",
                "body": "Mockups look great, proceeding with Phase 5 implementation.",
            },
        )
        draft = draft_res.json()

        # Send email with draft_id
        send_res = await client.post(
            "/api/v1/emails/send",
            json={
                "recipient": draft["recipient"],
                "subject": draft["subject"],
                "body": draft["body"],
                "draft_id": draft["id"],
            },
        )
        assert send_res.status_code == 200
        send_data = send_res.json()
        assert send_data["success"] is True
        assert "successfully sent" in send_data["message"]

        # Verify draft is now marked sent
        list_res = await client.get("/api/v1/emails/drafts?status=sent")
        assert list_res.status_code == 200
        sent_drafts = list_res.json()
        assert any(d["id"] == draft["id"] for d in sent_drafts)


@pytest.mark.asyncio
async def test_email_agentic_policy_gates():
    """Verify deterministic policy engine gates sensitive send_email while allowing safe search_emails."""
    search_dec = PolicyEngine.evaluate("search_emails", {"query": "interview"})
    assert search_dec.allowed is True
    assert search_dec.requires_approval is False

    send_dec = PolicyEngine.evaluate(
        "send_email",
        {"recipient": "recruiter@example.com", "subject": "Offer Accept", "body": "I accept"},
    )
    assert send_dec.allowed is True
    assert send_dec.requires_approval is True
    assert "Send email" in send_dec.action_summary

