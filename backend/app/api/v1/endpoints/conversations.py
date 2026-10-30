"""Conversations and message history endpoints."""

import uuid
from datetime import datetime
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database.session import get_db
from app.models.conversation import Conversation, Message

router = APIRouter()


class MessageRead(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"
    user_id: Optional[uuid.UUID] = None


class ConversationRead(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageRead] = []

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conv_in: ConversationCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new conversation session."""
    user_id = conv_in.user_id
    if not user_id:
        # Fallback to demo/first user if available
        from app.models.user import User
        res = await db.execute(select(User).limit(1))
        first_user = res.scalar_one_or_none()
        if first_user:
            user_id = first_user.id
        else:
            raise HTTPException(status_code=400, detail="User account required to create conversation.")

    conv = Conversation(
        title=conv_in.title or "New Conversation",
        user_id=user_id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)

    # Re-fetch with messages relation
    res = await db.execute(
        select(Conversation).options(selectinload(Conversation.messages)).where(Conversation.id == conv.id)
    )
    return res.scalar_one()


@router.get("", response_model=List[ConversationRead])
async def list_conversations(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List recent conversations."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get conversation details with message history."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
