"""Tests for the real email sending tool (send_email).

Tests run in offline mode (SMTP mocked) so they pass without real credentials.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestSendEmailOffline:
    """Tests that work without a real Gmail account (SMTP is mocked)."""

    def _get_tool(self):
        from agent.tools.email import send_email
        return send_email

    # ------------------------------------------------------------------ #
    # Missing / bad configuration
    # ------------------------------------------------------------------ #

    def test_missing_smtp_creds_returns_config_error(self):
        """When env vars are absent the tool should return a clear config error."""
        with patch.dict(os.environ, {"SENDER_EMAIL": "", "SENDER_APP_PASSWORD": ""}, clear=False):
            result = self._get_tool()(to="test@example.com", description="Hello world")
        assert result["success"] is False
        assert "configured" in result["spoken"].lower() or "smtp" in result["spoken"].lower()

    def test_missing_recipient_returns_error(self):
        result = self._get_tool()(to="", description="Hello world")
        assert result["success"] is False
        assert "email address" in result["spoken"].lower()

    def test_invalid_email_returns_error(self):
        result = self._get_tool()(to="not-an-email", description="Hello")
        assert result["success"] is False

    def test_missing_description_returns_error(self):
        with patch.dict(os.environ, {"SENDER_EMAIL": "me@gmail.com", "SENDER_APP_PASSWORD": "pass"}, clear=False):
            result = self._get_tool()(to="test@example.com", description=None)
        assert result["success"] is False

    # ------------------------------------------------------------------ #
    # AI composer (mocked OpenAI)
    # ------------------------------------------------------------------ #

    def test_ai_composer_called_with_description(self):
        """_compose_email should be called and its result used."""
        from agent.tools import email as email_mod
        fake_compose = {"subject": "Test Subject", "body": "Hello there, this is a test."}
        with patch.object(email_mod, "_compose_email", return_value=fake_compose) as mock_compose, \
             patch.object(email_mod, "_send_smtp", return_value={"success": True, "to": "a@b.com", "subject": "Test Subject"}):
            result = email_mod.send_email(to="a@b.com", description="say hello")
        mock_compose.assert_called_once_with("say hello", "")
        assert result["success"] is True

    def test_explicit_subject_body_skip_ai(self):
        """When subject AND body are both provided, AI composer should NOT be called."""
        from agent.tools import email as email_mod
        with patch.object(email_mod, "_compose_email") as mock_compose, \
             patch.object(email_mod, "_send_smtp", return_value={"success": True, "to": "x@y.com", "subject": "S"}):
            result = email_mod.send_email(to="x@y.com", description="ignored", subject="S", body="B")
        mock_compose.assert_not_called()
        assert result["success"] is True

    def test_recipient_name_passed_to_composer(self):
        from agent.tools import email as email_mod
        fake_compose = {"subject": "Hi Priya", "body": "Dear Priya, ..."}
        with patch.object(email_mod, "_compose_email", return_value=fake_compose) as mock_compose, \
             patch.object(email_mod, "_send_smtp", return_value={"success": True, "to": "p@g.com", "subject": "Hi Priya"}):
            email_mod.send_email(to="p@g.com", description="meeting moved", recipient_name="Priya")
        mock_compose.assert_called_once_with("meeting moved", "Priya")

    # ------------------------------------------------------------------ #
    # SMTP success path
    # ------------------------------------------------------------------ #

    def test_successful_send_returns_spoken_confirmation(self):
        from agent.tools import email as email_mod
        with patch.object(email_mod, "_compose_email", return_value={"subject": "Greetings", "body": "Hi!"}), \
             patch.object(email_mod, "_send_smtp", return_value={"success": True, "to": "bob@ex.com", "subject": "Greetings"}):
            result = email_mod.send_email(to="bob@ex.com", description="say hi")
        assert result["success"] is True
        assert "bob@ex.com" in result["spoken"] or "Greetings" in result["spoken"]
        assert result["subject"] == "Greetings"
        assert result["to"] == "bob@ex.com"

    def test_successful_send_includes_body(self):
        from agent.tools import email as email_mod
        with patch.object(email_mod, "_compose_email", return_value={"subject": "S", "body": "Body text"}), \
             patch.object(email_mod, "_send_smtp", return_value={"success": True, "to": "a@b.com", "subject": "S"}):
            result = email_mod.send_email(to="a@b.com", description="test")
        assert result.get("body") == "Body text"

    # ------------------------------------------------------------------ #
    # SMTP failure paths
    # ------------------------------------------------------------------ #

    def test_smtp_auth_failure_propagated(self):
        from agent.tools import email as email_mod
        fail = {"success": False, "error": "Authentication failed", "spoken": "Gmail authentication failed."}
        with patch.object(email_mod, "_compose_email", return_value={"subject": "S", "body": "B"}), \
             patch.object(email_mod, "_send_smtp", return_value=fail):
            result = email_mod.send_email(to="t@t.com", description="test")
        assert result["success"] is False
        assert "authentication" in result["spoken"].lower() or "failed" in result["spoken"].lower()

    # ------------------------------------------------------------------ #
    # Legacy stubs still work
    # ------------------------------------------------------------------ #

    def test_search_email_returns_results(self):
        from agent.tools.email import search_email
        r = search_email("Launch")
        assert r["success"] is True
        assert r["count"] > 0

    def test_summarize_email_works(self):
        from agent.tools.email import summarize_email
        r = summarize_email("msg-1")
        assert r["success"] is True
        assert "sarah" in r["spoken"].lower()

    def test_draft_reply_creates_draft(self):
        from agent.tools.email import draft_reply
        r = draft_reply(id="test@ex.com", points="Key points here")
        assert r["success"] is True
        assert r["draft_id"].startswith("draft-")
