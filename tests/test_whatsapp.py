"""Unit tests for WhatsApp Contact Search and Messaging Tool."""

import pytest
import uuid
from unittest.mock import patch
from agent.tools.whatsapp import send_whatsapp_message
from agent.main import process_user_turn


@patch("webbrowser.open_new_tab")
def test_send_whatsapp_with_name_and_message(mock_browser):
    mock_browser.return_value = True
    res = send_whatsapp_message(contact_name="Krish", message="Hiiii")
    assert res["success"] is True
    assert res["contact"] == "Krish"
    assert res["message"] == "Hiiii"
    assert "Krish" in res["spoken"]
    assert "Hiiii" in res["spoken"]
    mock_browser.assert_called_once_with("https://web.whatsapp.com")


@patch("webbrowser.open_new_tab")
def test_send_whatsapp_with_phone_number(mock_browser):
    mock_browser.return_value = True
    res = send_whatsapp_message(contact_name="Krish", message="Hiiii", phone="+919876543210")
    assert res["success"] is True
    assert "919876543210" in res["url"]
    assert "Hiiii" in res["url"]
    assert "Krish" in res["spoken"]
    mock_browser.assert_called_once()


def test_send_whatsapp_validation_no_contact():
    res = send_whatsapp_message(contact_name="")
    assert res["success"] is False
    assert "specify who you would like to message" in res["spoken"]


@pytest.mark.asyncio
@patch("webbrowser.open_new_tab")
async def test_agent_intent_open_whatsapp_and_message_krish(mock_browser):
    mock_browser.return_value = True
    s_id = f"test-wa-msg-{uuid.uuid4().hex[:6]}"
    turn = await process_user_turn(
        "open whatsapp and then open krish chat and then message him like Hiiii",
        session_id=s_id,
    )
    assert "krish" in turn["spoken_reply"].lower()
    tool_names = [tc["tool"] for tc in turn["tool_calls_executed"]]
    assert "send_whatsapp_message" in tool_names
    tc = [tc for tc in turn["tool_calls_executed"] if tc["tool"] == "send_whatsapp_message"][0]
    assert "krish" in tc["args"]["contact_name"].lower()
    if tc["args"].get("message"):
        assert "hi" in tc["args"]["message"].lower()

