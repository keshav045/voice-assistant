"""Unit tests for App and Website Launcher Tool."""

import pytest
import uuid
from unittest.mock import patch
from agent.tools.launcher import open_app, APP_SITES, launch_in_browser
from agent.main import process_user_turn


def test_open_app_targets_defined():
    assert "youtube" in APP_SITES
    assert "whatsapp" in APP_SITES
    assert "mail" in APP_SITES
    assert "linkedin" in APP_SITES
    assert "github" in APP_SITES
    assert "spotify" in APP_SITES


@patch("webbrowser.open_new_tab")
def test_open_youtube_general(mock_browser):
    mock_browser.return_value = True
    res = open_app("youtube")
    assert res["success"] is True
    assert res["target"] == "YouTube"
    assert "youtube.com" in res["url"]
    assert "Opening YouTube" in res["spoken"]


@patch("webbrowser.open_new_tab")
def test_open_youtube_with_query(mock_browser):
    mock_browser.return_value = True
    res = open_app("youtube", query="python tutorial")
    assert res["success"] is True
    assert "search_query=python+tutorial" in res["url"]
    assert "searching for 'python tutorial'" in res["spoken"]


@patch("webbrowser.open_new_tab")
@patch("agent.tools.launcher.is_windows_app_installed", return_value=False)
def test_open_whatsapp_browser_fallback(mock_installed, mock_browser):
    mock_browser.return_value = True
    res = open_app("whatsapp")
    assert res["success"] is True
    assert res["target"] == "WhatsApp"
    assert "web.whatsapp.com" in res["url"]
    assert "WhatsApp" in res["spoken"]


@patch("webbrowser.open_new_tab")
def test_open_gmail_mail(mock_browser):
    mock_browser.return_value = True
    res = open_app("mail")
    assert res["success"] is True
    assert "mail.google.com" in res["url"]

    res2 = open_app("gmail")
    assert res2["success"] is True
    assert "mail.google.com" in res2["url"]


@patch("webbrowser.open_new_tab")
def test_open_linkedin(mock_browser):
    mock_browser.return_value = True
    res = open_app("linkedin")
    assert res["success"] is True
    assert "linkedin.com" in res["url"]


@patch("webbrowser.open_new_tab")
def test_open_direct_url(mock_browser):
    mock_browser.return_value = True
    res = open_app("google", url="https://antigravity.google.com")
    assert res["success"] is True
    assert res["url"] == "https://antigravity.google.com"


@patch("webbrowser.open_new_tab")
def test_open_specific_browser(mock_browser):
    mock_browser.return_value = True
    res_chrome = open_app("youtube", browser="chrome")
    assert res_chrome["success"] is True
    assert res_chrome["browser"] == "chrome"

    res_edge = open_app("youtube", browser="edge")
    assert res_edge["success"] is True
    assert res_edge["browser"] == "edge"


@pytest.mark.asyncio
@patch("webbrowser.open_new_tab")
async def test_agent_intent_open_youtube(mock_browser):
    mock_browser.return_value = True
    s_id = f"test-yt-{uuid.uuid4().hex[:6]}"
    turn = await process_user_turn("open youtube", session_id=s_id)
    assert "youtube" in turn["spoken_reply"].lower()
    tool_names = [tc["tool"] for tc in turn["tool_calls_executed"]]
    assert "open_app" in tool_names


@pytest.mark.asyncio
@patch("webbrowser.open_new_tab")
async def test_agent_intent_open_whatsapp(mock_browser):
    mock_browser.return_value = True
    s_id = f"test-wa-{uuid.uuid4().hex[:6]}"
    turn = await process_user_turn("open whatsapp", session_id=s_id)
    assert "whatsapp" in turn["spoken_reply"].lower()
    tool_names = [tc["tool"] for tc in turn["tool_calls_executed"]]
    assert "open_app" in tool_names
