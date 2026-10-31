"""Semantic Memory Service with Vector Embeddings and Cosine Similarity."""

import hashlib
import logging
import math
from typing import Any, Dict, List, Optional
import uuid
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.memory import MemoryItem

logger = logging.getLogger("nexus.memory")


class MemoryService:
    """Manages text embedding generation, vector persistence, and cosine similarity search."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.openai_client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate 1536-dimensional vector embedding for text using OpenAI or deterministic offline projection."""
        clean_text = text.strip().replace("\n", " ")
        if not clean_text:
            return [0.0] * 1536

        if self.openai_client:
            try:
                response = await self.openai_client.embeddings.create(
                    model="text-embedding-3-small",
                    input=clean_text,
                )
                return response.data[0].embedding
            except Exception as e:
                logger.warning(f"OpenAI embedding generation failed, using deterministic local projection: {e}")

        # Deterministic 1536-dim normalized hash projection fallback for offline/local testing
        return self._generate_local_projection(clean_text)

    @staticmethod
    def _generate_local_projection(text: str, dimensions: int = 1536) -> List[float]:
        """Generate a dense semantic hash embedding using character n-grams and word tokens."""
        clean = text.lower()
        tokens = clean.split()
        vec = [0.0] * dimensions

        # 1. Word token hashing
        for t in tokens:
            h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
            idx = h % dimensions
            sign = 1.0 if ((h >> 16) & 1) else -1.0
            vec[idx] += 3.0 * sign

        # 2. Character n-gram hashing (3-grams and 4-grams) to capture morphological similarity
        for n in (3, 4):
            for i in range(len(clean) - n + 1):
                gram = clean[i : i + n]
                h = int(hashlib.sha256(gram.encode("utf-8")).hexdigest(), 16)
                idx = h % dimensions
                sign = 1.0 if ((h >> 16) & 1) else -1.0
                vec[idx] += 0.5 * sign

        # Unit normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [x / norm for x in vec]
        return [0.0] * dimensions


    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity between two float vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        score = dot_product / (norm_a * norm_b)
        # Clamp between -1.0 and 1.0 to guard against floating-point inaccuracies
        return max(-1.0, min(1.0, score))

    async def store_memory(
        self,
        db: AsyncSession,
        content: str,
        category: str = "fact",
        source: str = "conversation",
        confidence: float = 1.0,
        user_id: Optional[uuid.UUID] = None,
    ) -> MemoryItem:
        """Compute embedding and persist memory record in database."""
        embedding = await self.generate_embedding(content)
        item = MemoryItem(
            content=content,
            category=category,
            source=source,
            confidence=confidence,
            embedding=embedding,
            user_id=user_id,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    async def search_memories(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        min_similarity: float = 0.0,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-K most semantically relevant memories via cosine similarity ranking."""
        query_embedding = await self.generate_embedding(query)

        stmt = select(MemoryItem)
        if category:
            stmt = stmt.where(MemoryItem.category == category)
        if user_id:
            stmt = stmt.where(MemoryItem.user_id == user_id)

        result = await db.execute(stmt)
        memories = list(result.scalars().all())

        scored_results: List[Dict[str, Any]] = []
        for mem in memories:
            if not mem.embedding:
                continue
            sim = self.cosine_similarity(query_embedding, mem.embedding)
            if sim >= min_similarity:
                scored_results.append({
                    "id": str(mem.id),
                    "category": mem.category,
                    "content": mem.content,
                    "similarity": round(sim, 4),
                    "confidence": mem.confidence,
                    "source": mem.source,
                    "created_at": mem.created_at.isoformat() if mem.created_at else None,
                })

        # Sort descending by similarity score
        scored_results.sort(key=lambda x: x["similarity"], reverse=True)
        return scored_results[:top_k]

    async def list_memories(
        self,
        db: AsyncSession,
        category: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[MemoryItem]:
        """List stored memories ordered by creation date."""
        stmt = select(MemoryItem).order_by(MemoryItem.created_at.desc())
        if category:
            stmt = stmt.where(MemoryItem.category == category)
        if user_id:
            stmt = stmt.where(MemoryItem.user_id == user_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def delete_memory(self, db: AsyncSession, memory_id: uuid.UUID) -> bool:
        """Delete an individual memory record by ID."""
        stmt = select(MemoryItem).where(MemoryItem.id == memory_id)
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return False
        await db.delete(item)
        await db.commit()
        return True

    async def wipe_all_memories(self, db: AsyncSession, user_id: Optional[uuid.UUID] = None) -> int:
        """Wipe all user memories (Sensitive operation). Returns count of deleted records."""
        stmt = delete(MemoryItem)
        if user_id:
            stmt = stmt.where(MemoryItem.user_id == user_id)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount
