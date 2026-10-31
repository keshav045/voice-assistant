"""Specialist Semantic Memory Agent for storing and searching learned context."""

import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import MemoryItem
from app.services.memory_service import MemoryService


class MemoryAgent:
    """Specialist agent for semantic memory retrieval and persistence."""

    def __init__(self):
        self.service = MemoryService()

    async def store_memory(
        self,
        db: AsyncSession,
        content: str,
        category: str = "fact",
        source: str = "conversation",
        confidence: float = 1.0,
        user_id: Optional[uuid.UUID] = None,
    ) -> MemoryItem:
        """Store a new contextual fact or preference."""
        return await self.service.store_memory(
            db=db,
            content=content,
            category=category,
            source=source,
            confidence=confidence,
            user_id=user_id,
        )

    async def search_memories(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        min_similarity: float = 0.0,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Search memories semantically using vector similarity."""
        return await self.service.search_memories(
            db=db,
            query=query,
            top_k=top_k,
            category=category,
            min_similarity=min_similarity,
            user_id=user_id,
        )

    async def list_memories(
        self,
        db: AsyncSession,
        category: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[MemoryItem]:
        """List all stored memory records."""
        return await self.service.list_memories(db=db, category=category, user_id=user_id)

    async def delete_memory(
        self,
        db: AsyncSession,
        memory_id: uuid.UUID,
    ) -> bool:
        """Delete a single memory item."""
        return await self.service.delete_memory(db=db, memory_id=memory_id)

    async def wipe_memories(
        self,
        db: AsyncSession,
        user_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Wipe all stored memories (Sensitive operation)."""
        return await self.service.wipe_all_memories(db=db, user_id=user_id)
