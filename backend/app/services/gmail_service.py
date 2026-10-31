"""Gmail Integration and Email Management Service."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger("nexus.gmail")

# Curated sample inbox items for instant local testing and offline capability
SAMPLE_INBOX: List[Dict[str, Any]] = [
    {
        "id": "msg-inv-001",
        "sender": "talent-team@apextechnologies.io",
        "recipient": "keshav@nexus.ai",
        "subject": "Interview Invitation: Senior Agentic AI Architect",
        "date": "2026-10-30T14:30:00Z",
        "snippet": "We are excited to invite you for an interview tomorrow at 3:00 PM UTC...",
        "body": (
            "Hi Keshav,\n\n"
            "We were very impressed with your work on hybrid voice AI and autonomous agent orchestration. "
            "We would love to invite you for an interview tomorrow, Friday, at 3:00 PM UTC. "
            "Please confirm if this time works for you, or propose an alternative availability.\n\n"
            "Best regards,\nSarah Jenkins\nApex Technologies Recruiting"
        ),
        "is_read": False,
        "labels": ["INBOX", "IMPORTANT"],
    },
    {
        "id": "msg-proj-002",
        "sender": "lead-designer@nexus.ai",
        "recipient": "keshav@nexus.ai",
        "subject": "Design Review: Phase 5 & 6 Interface Components",
        "date": "2026-10-30T11:15:00Z",
        "snippet": "Attached are the high-fidelity mockups for the email composer and calendar...",
        "body": (
            "Hey Keshav,\n\n"
            "The design team has finished the review for the Email Assistant and Calendar views. "
            "The approval modal flows and dark mode typography have been updated. "
            "Let us know when you are ready to review.\n\n"
            "Cheers,\nAlex Rivera"
        ),
        "is_read": True,
        "labels": ["INBOX", "DESIGN"],
    },
    {
        "id": "msg-cloud-003",
        "sender": "billing-alerts@cloudplatform.com",
        "recipient": "keshav@nexus.ai",
        "subject": "Cloud Infrastructure Monthly Summary",
        "date": "2026-10-29T08:00:00Z",
        "snippet": "Your cloud compute invoice for the current period is ready for review...",
        "body": (
            "Hello,\n\n"
            "Your monthly cloud usage report is available. Compute instances and pgvector database clusters "
            "remained within the allocated development tier budget.\n\n"
            "Cloud Platform Team"
        ),
        "is_read": True,
        "labels": ["INBOX", "FINANCE"],
    },
]


class GmailService:
    """Manages email search, message retrieval, AI summarization, and draft creation."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.openai_client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def search_messages(self, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Search inbox messages matching keyword query."""
        if not query:
            return SAMPLE_INBOX[:limit]

        q = query.lower()
        results = [
            m for m in SAMPLE_INBOX
            if q in m["subject"].lower() or q in m["body"].lower() or q in m["sender"].lower()
        ]
        return results[:limit]

    async def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full message body by ID."""
        for m in SAMPLE_INBOX:
            if m["id"] == message_id:
                return m
        return None

    async def summarize_emails(self, query: str = "") -> Dict[str, Any]:
        """Summarize email threads matching query, extracting action items and meeting invitations."""
        messages = await self.search_messages(query=query, limit=5)
        if not messages:
            return {
                "summary": "No matching emails found for this search.",
                "action_items": [],
                "extracted_events": [],
            }

        combined_text = "\n\n---\n\n".join(
            [f"From: {m['sender']}\nSubject: {m['subject']}\nDate: {m['date']}\n\n{m['body']}" for m in messages]
        )

        if self.openai_client:
            try:
                system_prompt = (
                    "You are Nexus Email Intelligence. Analyze the following emails and provide:\n"
                    "1. A concise bullet summary of each key message\n"
                    "2. Any meeting or interview invitations (with date/time if mentioned)\n"
                    "3. Action items or follow-ups required by the user."
                )
                response = await self.openai_client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": combined_text},
                    ],
                    temperature=0.2,
                )
                summary_text = response.choices[0].message.content or ""
                return {
                    "summary": summary_text,
                    "emails_analyzed": len(messages),
                    "query": query,
                }
            except Exception as e:
                logger.warning(f"OpenAI summarization failed, falling back to extractive summary: {e}")

        # Extractive summarization fallback
        summary_lines = [f"Found {len(messages)} matching emails:"]
        for m in messages:
            summary_lines.append(f"• [{m['subject']}] from {m['sender']}: {m['snippet']}")

        return {
            "summary": "\n".join(summary_lines),
            "emails_analyzed": len(messages),
            "query": query,
        }

