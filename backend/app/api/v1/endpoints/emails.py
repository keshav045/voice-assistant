"""Gmail and Email Assistant REST API endpoints."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.email_agent import EmailAgent
from app.database.session import get_db

router = APIRouter()
email_agent = EmailAgent()


# --- Pydantic Schemas ---
class EmailDraftCreate(BaseModel):
    recipient: str
    subject: str
    body: str
    user_id: Optional[uuid.UUID] = None


class EmailDraftResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    recipient: str
    subject: str
    body: str
    status: str
    gmail_draft_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailSummarizeRequest(BaseModel):
    query: Optional[str] = ""


class EmailSummarizeResponse(BaseModel):
    success: bool
    summary: str
    emails_analyzed: int
    query: Optional[str] = ""


class EmailSendRequest(BaseModel):
    recipient: str
    subject: str
    body: str
    draft_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None


class EmailSendResponse(BaseModel):
    success: bool
    message: str
    sent_at: str
    recipient: str


class EmailSearchResponse(BaseModel):
    success: bool
    count: int
    messages: List[Dict[str, Any]]
    query: str


# --- Endpoints ---
@router.get("/search", response_model=EmailSearchResponse)
async def search_emails(
    q: str = Query("", description="Keywords, recipient or sender to search for"),
    limit: int = Query(10, ge=1, le=50, description="Max messages to return"),
) -> Any:
    """Search inbox messages matching keyword query."""
    return await email_agent.search_emails(query=q, limit=limit)


@router.post("/summarize", response_model=EmailSummarizeResponse)
async def summarize_emails(
    request: EmailSummarizeRequest,
) -> Any:
    """Summarize messages, extracting action items and invitations."""
    return await email_agent.summarize_thread(query=request.query or "")


@router.get("/drafts", response_model=List[EmailDraftResponse])
async def list_drafts(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List email drafts, optionally filtering by status."""
    return await email_agent.list_drafts(db=db, status=status_filter)


@router.post("/drafts", response_model=EmailDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_draft(
    draft_in: EmailDraftCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new email draft."""
    return await email_agent.create_draft(
        db=db,
        recipient=draft_in.recipient,
        subject=draft_in.subject,
        body=draft_in.body,
        user_id=draft_in.user_id,
    )


@router.post("/send", response_model=EmailSendResponse)
async def send_email(
    send_in: EmailSendRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Send an email and mark the draft as sent if draft_id is provided."""
    return await email_agent.send_email(
        db=db,
        recipient=send_in.recipient,
        subject=send_in.subject,
        body=send_in.body,
        draft_id=send_in.draft_id,
        user_id=send_in.user_id,
    )
