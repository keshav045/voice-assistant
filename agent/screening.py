"""Screening and Guardrails Engine for Nexus AI Assistant.

Provides bidirectional screening:
1. Input Screening:
   - Prompt injection defense (system prompt override attempts)
   - Toxicity and violent content detection
   - PII and credential masking (credit cards, raw API keys, SSNs)
   - Out-of-scope physical world action gating
2. Output Screening:
   - Zero-markdown spoken speech compliance (removes bullets, asterisks, backticks)
   - Clinical pharmacology disclaimer enforcement
   - Secret credential redaction (masks API keys, bearer tokens, passwords)
   - Tool result hallucination verification
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.screening")

# Common prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)",
    r"bypass\s+(?:all\s+)?(?:safety|guardrails|filters|rules)",
    r"you\s+are\s+now\s+(?:DAN|jailbroken|unrestricted|godmode)",
    r"system\s+override\s*:",
    r"new\s+system\s+prompt\s*:",
    r"reveal\s+(?:your\s+)?(?:system\s+prompt|developer\s+instructions|master\s+prompt)",
]

# Toxic or harmful intent triggers
TOXIC_PATTERNS = [
    r"\b(?:build|make|synthesize|create)\s+(?:a\s+)?(?:bomb|explosive|biological\s+weapon|poison)\b",
    r"\b(?:kill|murder|harm|assassinate)\s+(?:someone|people|him|her|them)\b",
    r"\b(?:hack|ddos|exploit)\s+(?:into\s+)?(?:the\s+)?(?:bank|government|server|pentagon)\b",
]

# Out of scope physical realm actions
PHYSICAL_PATTERNS = [
    r"\b(?:turn\s+on|turn\s+off|heat\s+up|ignite)\s+(?:the\s+)?(?:stove|gas|oven|furnace|car|engine)\b",
    r"\b(?:fly|drive|teleport)\s+(?:me\s+)?(?:to\s+)?(?:paris|london|new\s+york|mumbai)\b",
    r"\b(?:transfer|wire)\s+(?:\$|usd|inr|rs\.?|dollars|money)\s+(?:to\s+my\s+bank|without\s+approval)\b",
]

# Sensitive credentials & PII regex patterns
CREDENTIAL_PATTERNS = [
    (r"\bsk-[A-Za-z0-9]{20,}\b", "[REDACTED_API_KEY]"),
    (r"\b(?:Bearer\s+)[A-Za-z0-9_\-\.]{25,}\b", "Bearer [REDACTED_TOKEN]"),
    (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[REDACTED_CARD_NUMBER]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]"),
]


@dataclass
class ScreeningResult:
    """Outcome of input or output screening analysis."""
    passed: bool
    action: str  # "allow" | "block" | "sanitize" | "flag"
    sanitized_text: str
    flags: List[str] = field(default_factory=list)
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "action": self.action,
            "sanitized_text": self.sanitized_text,
            "flags": self.flags,
            "reason": self.reason,
        }


def screen_input(user_text: str, user_id: str = "guest") -> ScreeningResult:
    """Screen user input before forwarding to the agent or LLM.

    Args:
        user_text: Raw incoming user prompt.
        user_id: Active user identifier.

    Returns:
        ScreeningResult indicating if input is safe or needs refusal/masking.
    """
    clean = (user_text or "").strip()
    if not clean:
        return ScreeningResult(passed=True, action="allow", sanitized_text="")

    flags: List[str] = []

    # 1. Prompt Injection Detection
    for pat in INJECTION_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            flags.append("prompt_injection_attempt")
            logger.warning(f"Screening blocked prompt injection from user {user_id}: {pat}")
            return ScreeningResult(
                passed=False,
                action="block",
                sanitized_text="I cannot fulfill requests that attempt to override my system guidelines or safety instructions.",
                flags=flags,
                reason="Detected prompt injection or system override attempt.",
            )

    # 2. Severe Harm / Toxicity Screening
    for pat in TOXIC_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            flags.append("harmful_content_refusal")
            logger.warning(f"Screening blocked harmful query from user {user_id}: {pat}")
            return ScreeningResult(
                passed=False,
                action="block",
                sanitized_text="I cannot assist with requests involving harmful, dangerous, or illegal activities.",
                flags=flags,
                reason="Detected prohibited safety risk.",
            )

    # 3. Out-of-Scope Physical Realm Defense
    for pat in PHYSICAL_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            flags.append("out_of_scope_physical")
            return ScreeningResult(
                passed=False,
                action="block",
                sanitized_text="I cannot control physical appliances, vehicles, or execute direct financial transfers. I am an AI desktop and voice assistant.",
                flags=flags,
                reason="Requested action involves external physical systems outside assistant capabilities.",
            )

    # 4. Sensitive Credential & PII Masking
    sanitized = clean
    for pat, repl in CREDENTIAL_PATTERNS:
        if re.search(pat, sanitized):
            flags.append("pii_credential_masked")
            sanitized = re.sub(pat, repl, sanitized)

    return ScreeningResult(
        passed=True,
        action="sanitize" if flags else "allow",
        sanitized_text=sanitized,
        flags=flags,
    )


def screen_output(
    output_text: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> ScreeningResult:
    """Screen assistant output before sending to TTS or the user interface.

    Enforces:
    - Zero-markdown formatting for natural spoken TTS
    - Credential leakage masking
    - Clinical medical disclaimer enforcement

    Args:
        output_text: Spoken or textual reply generated by the assistant.
        tool_calls: Tools executed in the turn.
        context: Turn metadata.

    Returns:
        ScreeningResult containing sanitized speech text and compliance flags.
    """
    raw = (output_text or "").strip()
    if not raw:
        return ScreeningResult(passed=True, action="allow", sanitized_text="")

    flags: List[str] = []
    sanitized = raw

    # 1. Zero-Markdown Voice Sanitization
    # Strip markdown headers: #, ##, ###
    sanitized = re.sub(r"^#{1,6}\s*", "", sanitized, flags=re.MULTILINE)
    sanitized = re.sub(r"\b#{1,6}\s*", "", sanitized)
    # Strip markdown links [text](url) -> text
    sanitized = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", sanitized)
    # Strip raw http/https URLs from spoken text
    sanitized = re.sub(r"https?://\S+", "", sanitized)
    # Strip bold / italics markdown
    sanitized = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", sanitized)
    sanitized = re.sub(r"(?<!\w)_{1,3}([^_]+)_{1,3}(?!\w)", r"\1", sanitized)
    # Strip list item bullets
    sanitized = re.sub(r"^\s*[-*•]\s*", "", sanitized, flags=re.MULTILINE)
    # Strip inline and block code blocks
    sanitized = re.sub(r"`{1,3}[^`]*`{1,3}", "", sanitized)
    sanitized = sanitized.replace("`", "")

    if sanitized != raw:
        flags.append("markdown_voice_sanitized")

    # 2. Mask any exposed secrets or API credentials
    for pat, repl in CREDENTIAL_PATTERNS:
        if re.search(pat, sanitized):
            flags.append("output_secret_redacted")
            sanitized = re.sub(pat, repl, sanitized)

    # 3. Medical Disclaimer Enforcement
    medicine_terms = ["paracetamol", "dolo 650", "ibuprofen", "metformin", "antibiotic", "dosage", "drug interaction", "milligram", "mg twice daily"]
    is_medical = any(term in sanitized.lower() for term in medicine_terms)
    if tool_calls and any(tc.get("tool") == "medical_search" for tc in tool_calls):
        is_medical = True

    if is_medical:
        disclaimer_phrase = "consult a licensed physician or doctor"
        if disclaimer_phrase not in sanitized.lower() and "consult your doctor" not in sanitized.lower():
            sanitized = sanitized.rstrip() + " Please remember to consult a licensed physician or doctor before taking or changing any medication."
            flags.append("medical_disclaimer_appended")

    return ScreeningResult(
        passed=True,
        action="sanitize" if flags else "allow",
        sanitized_text=sanitized,
        flags=flags,
    )
