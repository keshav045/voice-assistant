"""Semantic Memory REST API endpoints."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.memory_agent import MemoryAgent
from app.database.session import get_db

router = APIRouter()
memory_agent = MemoryAgent()


# --- Pydantic Schemas ---
class MemoryCreateRequest(BaseModel):
    content: str
    category: str = "fact"  # "preference", "fact", "goal", "interaction", "system"
    confidence: float = 1.0
    source: str = "manual"
    user_id: Optional[uuid.UUID] = None


class MemoryResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    category: str
    content: str
    confidence: float
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemorySearchRequest(BaseModel):
    query: str
    top_k: int = 5
    category: Optional[str] = None
    min_similarity: float = 0.0


class MemorySearchResult(BaseModel):
    id: str
    category: str
    content: str
    similarity: float
    confidence: float
    source: str
    created_at: Optional[str] = None


class MemoryWipeRequest(BaseModel):
    approval_granted: bool = False


# --- Endpoints ---
@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    category: Optional[str] = Query(None, description="Optional category filter"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List stored contextual memories."""
    return await memory_agent.list_memories(db=db, category=category)


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def store_memory(
    request: MemoryCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Store a new fact, preference, or learned user context."""
    return await memory_agent.store_memory(
        db=db,
        content=request.content,
        category=request.category,
        confidence=request.confidence,
        source=request.source,
        user_id=request.user_id,
    )


@router.post("/search", response_model=List[MemorySearchResult])
async def search_memories(
    request: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Perform semantic vector similarity search across memories."""
    return await memory_agent.search_memories(
        db=db,
        query=request.query,
        top_k=request.top_k,
        category=request.category,
        min_similarity=request.min_similarity,
    )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Delete a specific memory record by ID."""
    deleted = await memory_agent.delete_memory(db=db, memory_id=memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record {memory_id} not found.",
        )
    return {"success": True, "message": f"Memory {memory_id} deleted."}


@router.delete("/wipe/all")
async def wipe_all_memories(
    request: MemoryWipeRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Wipe all semantic memories. Requires explicit human approval."""
    if not request.approval_granted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Policy Gate: Wiping all semantic memories requires explicit human approval.",
        )

    count = await memory_agent.wipe_memories(db=db)
    return {
        "success": True,
        "deleted_count": count,
        "message": f"Successfully wiped {count} memory records.",
    }
