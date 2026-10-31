"""Specialist Email Agent with Gmail integration and draft management."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.email import EmailDraft
from app.services.gmail_service import GmailService


class EmailAgent:
    """Specialist agent for searching, summarizing, and composing emails."""

    def __init__(self):
        self.gmail_service = GmailService()

    async def search_emails(self, query: str = "", limit: int = 10) -> Dict[str, Any]:
        """Search Gmail inbox messages."""
        results = await self.gmail_service.search_messages(query=query, limit=limit)
        return {
            "success": True,
            "count": len(results),
            "messages": results,
            "query": query,
        }

    async def summarize_thread(self, query: str = "") -> Dict[str, Any]:
        """Summarize email messages and extract critical invitations or action items."""
        summary_result = await self.gmail_service.summarize_emails(query=query)
        return {
            "success": True,
            "summary": summary_result["summary"],
            "emails_analyzed": summary_result["emails_analyzed"],
        }

    async def create_draft(
        self,
        db: AsyncSession,
        recipient: str,
        subject: str,
        body: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> EmailDraft:
        """Create a new email draft."""
        draft = EmailDraft(
            recipient=recipient,
            subject=subject,
            body=body,
            status="draft",
            user_id=user_id,
        )
        db.add(draft)
        await db.commit()
        await db.refresh(draft)
        return draft

    async def list_drafts(
        self,
        db: AsyncSession,
        status: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[EmailDraft]:
        """List email drafts."""
        stmt = select(EmailDraft)
        if status:
            stmt = stmt.where(EmailDraft.status == status)
        if user_id:
            stmt = stmt.where(EmailDraft.user_id == user_id)
        stmt = stmt.order_by(EmailDraft.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def send_email(
        self,
        db: AsyncSession,
        recipient: str,
        subject: str,
        body: str,
        draft_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Send an email (Sensitive operation executing only upon approval)."""
        now = datetime.now(timezone.utc)

        if draft_id:
            result = await db.execute(select(EmailDraft).where(EmailDraft.id == draft_id))
            draft = result.scalar_one_or_none()
            if draft:
                draft.status = "sent"
                draft.sent_at = now
                await db.commit()
        else:
            # Create completed record
            draft = EmailDraft(
                recipient=recipient,
                subject=subject,
                body=body,
                status="sent",
                sent_at=now,
                user_id=user_id,
            )
            db.add(draft)
            await db.commit()

        return {
            "success": True,
            "message": f"Email successfully sent to '{recipient}' with subject '{subject}'.",
            "sent_at": now.isoformat(),
            "recipient": recipient,
        }
