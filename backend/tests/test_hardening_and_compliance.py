"""Integration tests for Phase 10: Hardening, Rate Limiting, and Security Audit Logging."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.rate_limiter import SlidingWindowRateLimiter
from app.services.audit_logger import audit_logger


@pytest.mark.asyncio
async def test_rate_limiter_headers():
    """Verify rate limiter middleware attaches remaining request quota header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/system/config")
        assert res.status_code == 200
        assert "x-ratelimit-remaining" in res.headers
        remaining = int(res.headers["x-ratelimit-remaining"])
        assert remaining >= 0


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_unit():
    """Verify sliding window algorithm triggers 429 when threshold is breached."""
    limiter = SlidingWindowRateLimiter(default_limit=3, window_seconds=60)
    client_ip = "192.168.1.100"
    path = "/test-route"

    # 3 allowed requests
    allowed, rem, _ = limiter.is_allowed(client_ip, path)
    assert allowed is True
    assert rem == 2

    allowed, rem, _ = limiter.is_allowed(client_ip, path)
    assert allowed is True
    assert rem == 1

    allowed, rem, _ = limiter.is_allowed(client_ip, path)
    assert allowed is True
    assert rem == 0

    # 4th request must be blocked
    allowed, rem, retry_after = limiter.is_allowed(client_ip, path)
    assert allowed is False
    assert rem == 0
    assert retry_after > 0


@pytest.mark.asyncio
async def test_audit_logging_and_query():
    """Verify audit logger stores sensitive events and allows filtering."""
    # Emit test audit log
    audit_logger.log_event(
        event_type="tool_exec",
        action="send_email",
        status="approved",
        user_id="usr-test-123",
        client_ip="127.0.0.1",
        details={"recipient": "security@nexus.ai"},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/system/audit-logs?event_type=tool_exec")
        assert res.status_code == 200
        events = res.json()
        assert len(events) >= 1
        assert any(e["action"] == "send_email" and e["status"] == "approved" for e in events)


@pytest.mark.asyncio
async def test_system_config_hardening_capabilities():
    """Verify system config advertises security hardening capabilities."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/system/config")
        assert res.status_code == 200
        data = res.json()
        caps = data.get("capabilities", [])
        assert "audit_logging" in caps
        assert "rate_limiting" in caps
