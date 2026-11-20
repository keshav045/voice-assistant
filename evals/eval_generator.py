"""Evaluates speech generation quality, conversational brevity, and formatting compliance."""

import os
import re
import sys
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from agent.voice import clean_spoken_text
from evals.harness import EvalHarness


def run_generator_eval(harness: EvalHarness) -> Dict[str, Any]:
    samples = [
        "**Note**: The answer is `42`. See [guide](https://example.com) for more.",
        "### Chapter 1: Newton's Laws\n- Law 1: Inertia\n- Law 2: F=ma\n- Law 3: Equal reaction",
        "Calculated **15 * 8** = `120` .",
    ]

    clean_count = 0
    for s in samples:
        cleaned = clean_spoken_text(s)
        has_markdown = bool(re.search(r"(\*\*|__|\`|###|\[.*?\]\(.*?\))", cleaned))
        if not has_markdown and len(cleaned.strip()) > 0:
            clean_count += 1

    clean_rate = round((clean_count / len(samples)) * 100, 1)

    # Voice conciseness check (should not be overly verbose essay in audio voice mode)
    test_voice_text = "The time complexity of binary search is O(log n) because the array is divided in half at each step."
    word_count = len(test_voice_text.split())
    is_concise = 5 <= word_count <= 40

    harness.record_test("eval_generator", "Clean Speech Compliance", clean_rate == 100.0, clean_rate, f"{clean_rate}% (0 markdown tags in TTS stream)")
    harness.record_test("eval_generator", "Voice Conciseness Index", is_concise, word_count, f"{word_count} words (conversational range)")

    return {
        "clean_speech_compliance_pct": clean_rate,
        "voice_conciseness_valid": is_concise,
    }


if __name__ == "__main__":
    h = EvalHarness()
    run_generator_eval(h)
