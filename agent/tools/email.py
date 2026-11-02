"""Email tools (Gmail / IMAP / drafts)."""

import uuid
from typing import Any, Dict, List, Optional

_SAMPLE_EMAILS: Dict[str, Dict[str, Any]] = {
    "msg-1": {
        "id": "msg-1",
        "sender": "sarah.chen@company.com",
        "subject": "Launch blockers for v2.4",
        "snippet": "Database migration index completed cleanly. Staging environment is resolved, awaiting design signoff.",
        "date": "Today, 08:30 AM",
        "unread": True,
    },
    "msg-2": {
        "id": "msg-2",
        "sender": "rahul.sharma@partner.com",
        "subject": "Proposal for Q4 Integration",
        "snippet": "Attached the JTBD matrix and revised API pricing tiers for your review.",
        "date": "Yesterday, 04:15 PM",
        "unread": False,
    },
}

_DRAFTS_STORE: Dict[str, Dict[str, Any]] = {}


def search_email(query: str = "") -> Dict[str, Any]:
    """Search inbox for email messages matching keywords or sender."""
    q = query.lower()
    matches = [
        m for m in _SAMPLE_EMAILS.values()
        if not q or q in m["subject"].lower() or q in m["snippet"].lower() or q in m["sender"].lower()
    ]
    if not matches:
        return {"success": True, "count": 0, "emails": [], "spoken": f"No emails found matching '{query}'."}

    spoken = f"Found {len(matches)} email{'s' if len(matches) > 1 else ''}. The latest is from {matches[0]['sender']} about {matches[0]['subject']}."
    return {"success": True, "count": len(matches), "emails": matches, "spoken": spoken}


def summarize_email(id: Optional[str] = None) -> Dict[str, Any]:
    """Provide a short spoken summary of an email by ID or sender."""
    if not id:
        email = list(_SAMPLE_EMAILS.values())[0] if _SAMPLE_EMAILS else None
    else:
        email = _SAMPLE_EMAILS.get(id)
        if not email:
            for m in _SAMPLE_EMAILS.values():
                if id.lower() in m["sender"].lower() or id.lower() in m["subject"].lower():
                    email = m
                    break

    if not email:
        return {"success": False, "spoken": f"Could not find an email matching '{id}'."}

    spoken = f"Email from {email['sender']} regarding {email['subject']}: {email['snippet']}"
    return {"success": True, "email": email, "spoken": spoken}


def draft_reply(id: Optional[str] = None, points: Optional[str] = None, to: Optional[str] = None, subject: Optional[str] = None, body: Optional[str] = None) -> Dict[str, Any]:
    """Create an email draft response without sending.
    
    Safe operation, does not send the email.
    """
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


def send_email(draft_id: Optional[str] = None, to: Optional[str] = None, subject: Optional[str] = None, body: Optional[str] = None) -> Dict[str, Any]:
    """Send an email draft to the recipient.
    
    High risk operation: requires explicit read-back and confirmation.
    """
    target_id = draft_id or f"draft-{uuid.uuid4().hex[:6]}"
    draft = _DRAFTS_STORE.get(target_id) or {"id": target_id, "to": to, "subject": subject, "body": body, "status": "sent"}
    draft["status"] = "sent"
    recipient = to or draft.get("reply_to") or "recipient"
    return {
        "success": True,
        "draft_id": target_id,
        "status": "sent",
        "spoken": f"Dispatched email to {recipient} successfully.",
    }
