"""Tests for Voice Assistant features: calculator and session memory."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from agent.tools.calc import calculator
from agent.session import add_turn, get_messages_for_prompt, clear_session


# ---------------------------------------------------------------------------
# Calculator tests
# ---------------------------------------------------------------------------

class TestCalculator:
    def test_basic_addition(self):
        r = calculator("2 + 2")
        assert r["success"] is True
        assert r["result"] == 4.0

    def test_percentage_of(self):
        r = calculator("15% of 2340")
        assert r["success"] is True
        assert r["result"] == pytest.approx(351.0)

    def test_sqrt(self):
        r = calculator("sqrt(144)")
        assert r["success"] is True
        assert r["result"] == pytest.approx(12.0)

    def test_power(self):
        r = calculator("2**8")
        assert r["success"] is True
        assert r["result"] == 256.0

    def test_division(self):
        r = calculator("100 / 4")
        assert r["success"] is True
        assert r["result"] == 25.0

    def test_floor_division(self):
        r = calculator("10 // 3")
        assert r["success"] is True
        assert r["result"] == 3.0

    def test_modulo(self):
        r = calculator("10 % 3")
        assert r["success"] is True
        assert r["result"] == 1.0

    def test_zero_division(self):
        r = calculator("1 / 0")
        assert r["success"] is False
        assert "zero" in r["spoken"].lower()

    def test_invalid_expression(self):
        r = calculator("import os")
        assert r["success"] is False

    def test_negative_number(self):
        r = calculator("-5 + 10")
        assert r["success"] is True
        assert r["result"] == 5.0

    def test_spoken_output(self):
        r = calculator("2 + 2")
        assert "4" in r["spoken"]


# ---------------------------------------------------------------------------
# Session memory tests
# ---------------------------------------------------------------------------

class TestSessionMemory:
    def test_empty_session_returns_empty_list(self):
        clear_session("test-empty")
        msgs = get_messages_for_prompt("test-empty")
        assert msgs == []

    def test_add_turn_stores_messages(self):
        clear_session("test-turn")
        add_turn("test-turn", "Hello", "Hi there!")
        msgs = get_messages_for_prompt("test-turn")
        assert any(m["role"] == "user" and m["content"] == "Hello" for m in msgs)
        assert any(m["role"] == "assistant" and m["content"] == "Hi there!" for m in msgs)

    def test_multiple_turns(self):
        clear_session("test-multi")
        add_turn("test-multi", "Q1", "A1")
        add_turn("test-multi", "Q2", "A2")
        msgs = get_messages_for_prompt("test-multi")
        assert len(msgs) == 4  # 2 turns × 2 messages

    def test_session_isolation(self):
        clear_session("sess-a")
        clear_session("sess-b")
        add_turn("sess-a", "Only in A", "Answer A")
        msgs_b = get_messages_for_prompt("sess-b")
        assert not any(m["content"] == "Only in A" for m in msgs_b)

    def test_clear_session(self):
        add_turn("test-clear", "Q", "A")
        clear_session("test-clear")
        msgs = get_messages_for_prompt("test-clear")
        assert msgs == []


