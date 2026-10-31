"""Integration tests for Phase 8: Semantic Memory & Vector Search."""

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
async def test_store_and_list_memories():
    """Verify storing user facts and retrieving filtered memories."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Store preference
        pref_payload = {
            "content": "Prefers concise email responses with bullet points.",
            "category": "preference",
            "source": "manual",
        }
        res_pref = await client.post("/api/v1/memory", json=pref_payload)
        assert res_pref.status_code == 201
        pref_data = res_pref.json()
        assert pref_data["category"] == "preference"
        assert pref_data["content"] == pref_payload["content"]
        pref_id = pref_data["id"]

        # Store fact
        fact_payload = {
            "content": "Working on Nexus Agentic AI assistant project.",
            "category": "fact",
            "source": "manual",
        }
        res_fact = await client.post("/api/v1/memory", json=fact_payload)
        assert res_fact.status_code == 201

        # List all
        list_res = await client.get("/api/v1/memory")
        assert list_res.status_code == 200
        memories = list_res.json()
        assert len(memories) >= 2

        # List category filter
        filter_res = await client.get("/api/v1/memory?category=preference")
        assert filter_res.status_code == 200
        filtered = filter_res.json()
        assert all(m["category"] == "preference" for m in filtered)


@pytest.mark.asyncio
async def test_semantic_vector_search():
    """Verify semantic vector search ranks relevant memory higher via cosine similarity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed two distinct semantic concepts
        await client.post(
            "/api/v1/memory",
            json={
                "content": "User loves coding in Python FastAPI and React TypeScript interfaces.",
                "category": "preference",
            },
        )
        await client.post(
            "/api/v1/memory",
            json={
                "content": "User enjoys weekend mountaineering and trail running outdoors.",
                "category": "fact",
            },
        )

        # Search for software engineering terms
        search_res = await client.post(
            "/api/v1/memory/search",
            json={
                "query": "What coding languages and Python tools does the user prefer?",
                "top_k": 2,
            },
        )
        assert search_res.status_code == 200
        results = search_res.json()
        assert len(results) >= 1
        top_hit = results[0]
        # The programming memory should be ranked highest
        assert "FastAPI" in top_hit["content"] or "Python" in top_hit["content"]
        assert top_hit["similarity"] > 0.0



@pytest.mark.asyncio
async def test_memory_delete_and_wipe_policy():
    """Verify individual memory deletion and approval-gated memory wiping."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Store a temp item
        temp_res = await client.post(
            "/api/v1/memory",
            json={"content": "Temporary test note to be deleted.", "category": "fact"},
        )
        item_id = temp_res.json()["id"]

        # Delete single item
        del_res = await client.delete(f"/api/v1/memory/{item_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # Policy test: Wipe memories without approval -> 403 Forbidden
        unauth_wipe = await client.request(
            "DELETE",
            "/api/v1/memory/wipe/all",
            json={"approval_granted": False},
        )
        assert unauth_wipe.status_code == 403
        assert "requires explicit human approval" in unauth_wipe.json()["detail"]

        # Policy test: Wipe memories with approval granted -> 200 OK
        auth_wipe = await client.request(
            "DELETE",
            "/api/v1/memory/wipe/all",
            json={"approval_granted": True},
        )
        assert auth_wipe.status_code == 200
        assert auth_wipe.json()["success"] is True


@pytest.mark.asyncio
async def test_memory_policy_engine_rules():
    """Verify deterministic policy engine gates wipe_memory while allowing retrieve_memory."""
    read_dec = PolicyEngine.evaluate("retrieve_memory", {"query": "languages"})
    assert read_dec.allowed is True
    assert read_dec.requires_approval is False

    wipe_dec = PolicyEngine.evaluate("wipe_memory", {})
    assert wipe_dec.allowed is True
    assert wipe_dec.requires_approval is True
    assert "Wipe" in wipe_dec.action_summary
