"""Unit and integration tests for Google Workspace OAuth 2.0 endpoints and Fernet token encryption."""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.core.security import decrypt_oauth_token, encrypt_oauth_token
from app.database.session import AsyncSessionLocal, init_db
from app.main import app
from app.models.user import OAuthAccount, User


@pytest.fixture(autouse=True)
async def setup_database():
    """Ensure database tables are initialized before tests."""
    await init_db()


def test_fernet_token_encryption_and_decryption():
    """Verify that OAuth tokens are symmetrically encrypted and correctly decrypted."""
    raw_token = "ya29.a0AfH6SMD-sample-google-oauth-access-token-12345"
    encrypted = encrypt_oauth_token(raw_token)

    assert encrypted != raw_token
    assert len(encrypted) > 20

    decrypted = decrypt_oauth_token(encrypted)
    assert decrypted == raw_token

    # Edge cases
    assert encrypt_oauth_token("") == ""
    assert decrypt_oauth_token("") == ""


@pytest.mark.asyncio
async def test_google_auth_url_endpoint():
    """Test generating Google OAuth authorization URL."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/auth/google/url")
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "redirect_uri" in data
        assert "http://localhost:8000/api/v1/auth/google/callback" in data["redirect_uri"]


@pytest.mark.asyncio
async def test_google_auth_status_endpoint():
    """Test fetching Google connection status when disconnected."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/auth/google/status")
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "connected" in data


@pytest.mark.asyncio
async def test_google_disconnect_workflow():
    """Test disconnecting a connected Google OAuth account."""
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"google.tester.{uuid.uuid4().hex[:6]}@gmail.com",
            hashed_password="fakehashfortest",
            full_name="Google Tester",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        oa = OAuthAccount(
            user_id=user.id,
            provider="google",
            provider_user_id="google-sub-12345",
            encrypted_access_token=encrypt_oauth_token("mock-google-token"),
            scopes="email profile gmail calendar",
        )
        session.add(oa)
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Check status
        res = await client.get("/api/v1/auth/google/status")
        assert res.status_code == 200

        # Disconnect
        disc_res = await client.post("/api/v1/auth/google/disconnect")
        assert disc_res.status_code == 200
        assert disc_res.json()["success"] is True
