"""Integration tests for Phase 1 Foundation: Health, System Config, and Auth."""

import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database.session import init_db


@pytest.fixture(autouse=True)
async def setup_database():
    """Ensure database tables are initialized before tests."""
    await init_db()


@pytest.mark.asyncio
async def test_root_health():
    """Test root /health endpoint reports healthy status and DB connectivity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "database" in data
        assert data["database"]["status"] == "connected"
        assert "version" in data


@pytest.mark.asyncio
async def test_api_v1_health():
    """Test /api/v1/health endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"]["status"] == "connected"


@pytest.mark.asyncio
async def test_system_config():
    """Test /api/v1/system/config returns valid capabilities and configuration."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/system/config")
        assert response.status_code == 200
        data = response.json()
        assert data["project_name"] == "Nexus Agentic AI Assistant"
        assert "capabilities" in data
        assert "voice_streaming" in data["capabilities"]
        assert "ai" in data


@pytest.mark.asyncio
async def test_auth_workflow():
    """Test user registration, login, and profile fetching."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register new user with unique email
        test_email = f"testuser_{uuid.uuid4().hex[:8]}@nexus.ai"
        test_password = "securePassword123!"
        reg_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": test_email,
                "password": test_password,
                "full_name": "Nexus Tester",
            },
        )
        assert reg_response.status_code == 201
        reg_data = reg_response.json()
        assert "access_token" in reg_data
        assert reg_data["user"]["email"] == test_email

        # 2. Login
        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": test_email,
                "password": test_password,
            },
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # 3. Access protected /me endpoint
        me_response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["email"] == test_email
        assert me_response.json()["full_name"] == "Nexus Tester"

