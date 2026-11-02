"""Tests for voice recording, speech-to-text, and audio playback."""

import threading
import numpy as np
import pytest

from agent.voice import clean_spoken_text, record_audio_push_to_talk, transcribe_audio, DEFAULT_SAMPLERATE


def test_clean_spoken_text():
    # Markdown headers, bold, italics, backticks, links
    raw = "### **India** vs *New Zealand* match! [Link](https://cricinfo.com) `score: 200`."
    cleaned = clean_spoken_text(raw)
    assert "**" not in cleaned
    assert "###" not in cleaned
    assert "`" not in cleaned
    assert "https://" not in cleaned
    assert "India vs New Zealand match! Link score: 200." == cleaned


def test_clean_spoken_text_empty():
    assert clean_spoken_text("") == ""
    assert clean_spoken_text(None) == ""


def test_transcribe_silent_audio():
    # Silent audio below threshold should return empty string without failing
    silent_audio = np.zeros(DEFAULT_SAMPLERATE, dtype=np.int16)
    res = transcribe_audio(silent_audio)
    assert res == ""


def test_push_to_talk_stop_event():
    # Setting stop_event immediately should return empty or near-empty array without hanging
    stop_event = threading.Event()
    stop_event.set()
    audio = record_audio_push_to_talk(stop_event)
    assert isinstance(audio, np.ndarray)
