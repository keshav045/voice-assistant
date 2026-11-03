"""Email tools — real SMTP sending via Gmail + AI subject/body composer.

Setup (one-time):
  1. Go to Google Account > Security > 2-Step Verification > App Passwords
  2. Generate an App Password for "Mail" on "Windows Computer"
  3. Add to .env:
        SENDER_EMAIL=your@gmail.com
        SENDER_APP_PASSWORD=xxxx xxxx xxxx xxxx

Voice usage examples:
  "Send an email to john@example.com about the project deadline"
  "Mail Priya at priya@gmail.com that the meeting is shifted to Friday 3pm"
  "Send a professional email to boss@company.com saying I will be late today"
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

logger = logging.getLogger("voice_assistant.email")

# --------------------------------------------------------------------------- #
# SMTP configuration (reads from environment at call time)
# --------------------------------------------------------------------------- #

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _get_smtp_creds() -> tuple[str, str]:
    """Return (sender_email, app_password) from environment."""
    sender = os.environ.get("SENDER_EMAIL", "").strip()
    password = os.environ.get("SENDER_APP_PASSWORD", "").strip()
    return sender, password


def _smtp_configured() -> bool:
    sender, password = _get_smtp_creds()
    return bool(sender and password)


# --------------------------------------------------------------------------- #
# AI subject + body composer (uses OpenAI synchronously — light call)
# --------------------------------------------------------------------------- #

def _compose_email(description: str, recipient_name: str = "") -> Dict[str, str]:
    """Use OpenAI to generate a professional subject and body from a brief description.
    Falls back to a simple template if the API key is missing.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        # Simple fallback without AI
        subject = f"Message{' for ' + recipient_name if recipient_name else ''}"
        body = description
        return {"subject": subject, "body": body}

    try:
        from openai import OpenAI  # synchronous client
        client = OpenAI(api_key=api_key)

        prompt = f"""You are a professional email assistant.
A user wants to send an email. Their description is:
"{description}"

{"Recipient name: " + recipient_name if recipient_name else ""}

Generate a concise, professional email.
Respond ONLY with valid JSON in this exact format (no markdown, no extra text):
{{
  "subject": "<email subject line>",
  "body": "<full email body with greeting and sign-off>"
}}"""

        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=400,
        )

        import json
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        raw = raw.strip("```json").strip("```").strip()
        result = json.loads(raw)
        return {
            "subject": result.get("subject", "No Subject"),
            "body": result.get("body", description),
        }
    except Exception as e:
        logger.warning(f"AI compose failed, using fallback: {e}")
        return {
            "subject": f"Message{' for ' + recipient_name if recipient_name else ''}",
            "body": description,
        }


# --------------------------------------------------------------------------- #
# Core sending function
# --------------------------------------------------------------------------- #

def _send_smtp(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    """Send email via Gmail SMTP with TLS. Returns result dict."""
    sender_email, app_password = _get_smtp_creds()

    if not sender_email or not app_password:
        return {
            "success": False,
            "error": "SMTP not configured",
            "spoken": (
                "Email not configured. Please add your SENDER_EMAIL and "
                "SENDER_APP_PASSWORD to the dot-env file and restart the assistant."
            ),
        }

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    # Plain-text part
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Optional HTML part (just wrap body in a simple <p>)
    html_body = f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender_email, app_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        logger.info(f"Email sent to {to_email} | subject: {subject}")
        return {"success": True, "to": to_email, "subject": subject}
    except smtplib.SMTPAuthenticationError:
        return {
            "success": False,
            "error": "Authentication failed",
            "spoken": (
                "Gmail authentication failed. Please check your SENDER_APP_PASSWORD. "
                "Make sure you are using a Gmail App Password, not your regular password."
            ),
        }
    except smtplib.SMTPException as e:
        return {"success": False, "error": str(e), "spoken": f"SMTP error: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e), "spoken": f"Failed to send email: {e}"}


# --------------------------------------------------------------------------- #
# Public tool: send_email — the one registered in TOOLS_REGISTRY
# --------------------------------------------------------------------------- #

def send_email(
    to: str,
    description: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    recipient_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a real email to a recipient.

    The AI will auto-generate a professional subject and body from the
    user's plain-language description if subject/body are not supplied.

    Args:
        to:             Recipient email address (required).
        description:    Natural-language description of what to say, e.g.
                        "Tell him the meeting is moved to Friday 3pm".
        subject:        Optional explicit subject line (overrides AI generation).
        body:           Optional explicit email body (overrides AI generation).
        recipient_name: Optional name used to personalise the AI-composed email.

    Returns:
        dict with keys: success (bool), spoken (str), to, subject.
    """
    to = (to or "").strip()
    if not to or "@" not in to:
        return {
            "success": False,
            "spoken": "I need a valid email address to send the mail. Could you provide the recipient's email?",
        }

    # Determine subject + body
    if subject and body:
        final_subject = subject
        final_body = body
    elif description:
        composed = _compose_email(description, recipient_name or "")
        final_subject = subject or composed["subject"]
        final_body = body or composed["body"]
    else:
        return {
            "success": False,
            "spoken": "Please describe what you want to say in the email.",
        }

    result = _send_smtp(to_email=to, subject=final_subject, body=final_body)

    if result["success"]:
        name_part = f" to {recipient_name}" if recipient_name else f" to {to}"
        result["spoken"] = (
            f"Done! I've sent the email{name_part} with the subject \"{final_subject}\"."
        )
        result["subject"] = final_subject
        result["body"] = final_body
        result["to"] = to

    return result


# --------------------------------------------------------------------------- #
# Legacy stub functions (kept so existing imports in test_agent.py don't break)
# --------------------------------------------------------------------------- #

_SAMPLE_EMAILS: Dict[str, Dict[str, Any]] = {
    "msg-1": {
        "id": "msg-1",
        "sender": "sarah.chen@company.com",
        "subject": "Launch blockers for v2.4",
        "snippet": "Database migration completed. Staging resolved, awaiting design signoff.",
        "date": "Today, 08:30 AM",
        "unread": True,
    },
}

_DRAFTS_STORE: Dict[str, Dict[str, Any]] = {}


def search_email(query: str = "") -> Dict[str, Any]:
    """Search inbox stub."""
    q = query.lower()
    matches = [
        m for m in _SAMPLE_EMAILS.values()
        if not q or q in m["subject"].lower() or q in m["snippet"].lower() or q in m["sender"].lower()
    ]
    if not matches:
        return {"success": True, "count": 0, "emails": [], "spoken": f"No emails found matching '{query}'."}
    spoken = f"Found {len(matches)} email. The latest is from {matches[0]['sender']} about {matches[0]['subject']}."
    return {"success": True, "count": len(matches), "emails": matches, "spoken": spoken}


def summarize_email(id: Optional[str] = None) -> Dict[str, Any]:
    """Summarise email stub."""
    email = _SAMPLE_EMAILS.get(id or "msg-1") or next(iter(_SAMPLE_EMAILS.values()), None)
    if not email:
        return {"success": False, "spoken": f"Could not find an email matching '{id}'."}
    spoken = f"Email from {email['sender']} regarding {email['subject']}: {email['snippet']}"
    return {"success": True, "email": email, "spoken": spoken}


def draft_reply(
    id: Optional[str] = None,
    points: Optional[str] = None,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a draft without sending."""
    draft_id = f"draft-{uuid.uuid4().hex[:6]}"
    target_to = to or id or "recipient@example.com"
    content = body or points or "Thank you for the update."
    draft = {
        "id": draft_id,
        "reply_to": target_to,
        "subject": subject or "Re: Update",
        "body": content,
        "status": "draft",
    }
    _DRAFTS_STORE[draft_id] = draft
    return {
        "success": True,
        "draft_id": draft_id,
        "draft": draft,
        "spoken": f"Created a draft reply to {target_to}. You can review or ask me to send it.",
    }
