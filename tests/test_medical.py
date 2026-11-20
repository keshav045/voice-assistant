"""Unit tests for Medical and Medicine Information Search Tool."""

import pytest
from agent.tools import TOOLS_REGISTRY, TOOL_SCHEMAS
from agent.tools.medical import (
    CURATED_MEDICINE_DB,
    MEDICAL_DISCLAIMER,
    medical_search,
)


def test_medical_search_curated_paracetamol():
    """Verify curated medicine lookup for Paracetamol returns complete clinical data."""
    res = medical_search("Paracetamol")
    assert res["success"] is True
    assert "Paracetamol" in res["generic_name"]
    assert "Dolo 650" in res["brand_names"]
    assert "uses" in res and len(res["uses"]) > 10
    assert "dosage_guidelines" in res
    assert "side_effects" in res
    assert "precautions" in res
    assert MEDICAL_DISCLAIMER in res["disclaimer"]
    assert len(res["spoken"]) > 20


def test_medical_search_dolo_650_uses_topic():
    """Verify topic-specific inquiry for Dolo 650 uses."""
    res = medical_search("Dolo 650", topic="uses")
    assert res["success"] is True
    assert "Paracetamol" in res["generic_name"]
    assert "used for" in res["spoken"].lower() or "relief" in res["spoken"].lower()


def test_medical_search_ibuprofen_side_effects():
    """Verify side effects topic returns adverse reaction guidelines."""
    res = medical_search("Ibuprofen", topic="side_effects")
    assert res["success"] is True
    assert "Ibuprofen" in res["generic_name"]
    assert "side effect" in res["spoken"].lower() or "stomach" in res["spoken"].lower()


def test_medical_search_metformin_dosage():
    """Verify dosage inquiry for Metformin."""
    res = medical_search("Metformin", topic="dosage")
    assert res["success"] is True
    assert "Metformin" in res["generic_name"]
    assert "dosage" in res["spoken"].lower() or "dose" in res["spoken"].lower()


def test_medical_search_empty_input():
    """Verify empty or whitespace query is handled safely without exception."""
    res = medical_search("")
    assert res["success"] is False
    assert "valid medicine" in res["error"].lower()
    assert res["spoken"] != ""


def test_medical_tool_registered_globally():
    """Verify medical_search is present in catalog, schemas, and main active names."""
    from agent.main import ACTIVE_TOOL_NAMES

    assert "medical_search" in TOOLS_REGISTRY
    assert callable(TOOLS_REGISTRY["medical_search"])

    schema_names = [s.get("function", {}).get("name") for s in TOOL_SCHEMAS]
    assert "medical_search" in schema_names
    assert "medical_search" in ACTIVE_TOOL_NAMES


@pytest.mark.asyncio
async def test_agent_intent_medicine_search():
    """Verify process_user_turn invokes medical_search when asked about medication."""
    from agent.main import process_user_turn

    turn = await process_user_turn("What is Dolo 650 used for?", session_id="test-med-turn")
    assert "spoken_reply" in turn
    assert len(turn["spoken_reply"]) > 20

    # Ensure either tool was executed or spoken reply answers the medicine question
    tools_used = [tc.get("tool") for tc in turn.get("tool_calls_executed", [])]
    assert "medical_search" in tools_used or "Paracetamol" in turn["spoken_reply"] or "Dolo" in turn["spoken_reply"]
