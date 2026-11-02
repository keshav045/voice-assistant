"""Vector store wrapper for Personal Documents (RAG)."""

import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from db.models import get_db_connection

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def compute_embedding(text: str) -> List[float]:
    """Compute vector embedding using OpenAI or deterministic fallback."""
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your-"):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            res = client.embeddings.create(input=text[:8000], model="text-embedding-3-small")
            return res.data[0].embedding
        except Exception:
            pass

    # Deterministic semantic hash embedding fallback (64-dim)
    words = text.lower().split()
    dim = 64
    vec = [0.0] * dim
    for i, w in enumerate(words):
        h = hash(w) % dim
        vec[h] += 1.0 / (1.0 + math.log(i + 1))
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1)) or 1.0
    norm2 = math.sqrt(sum(b * b for b in v2)) or 1.0
    return dot / (norm1 * norm2)


def add_doc_chunk(file_name: str, text: str, section: Optional[str] = None) -> str:
    """Store a document chunk with embedding in doc_chunks."""
    chunk_id = f"chunk-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    emb = compute_embedding(text)
    emb_json = json.dumps(emb)

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO doc_chunks (id, file, section, text, embedding, modified_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, file_name, section or "", text, emb_json, now),
        )
        conn.commit()
    return chunk_id


def search_doc_chunks(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Search document chunks by semantic cosine similarity."""
    query_emb = compute_embedding(query)
    results = []

    with get_db_connection() as conn:
        cur = conn.execute("SELECT id, file, section, text, embedding, modified_at FROM doc_chunks")
        rows = cur.fetchall()

    for row in rows:
        row_dict = dict(row)
        try:
            emb = json.loads(row_dict["embedding"]) if row_dict.get("embedding") else []
            sim = cosine_similarity(query_emb, emb)
            # Add lexical boost for exact keyword matches
            q_words = query.lower().split()
            text_lower = row_dict["text"].lower()
            keyword_matches = sum(1 for w in q_words if w in text_lower)
            lexical_boost = (keyword_matches / len(q_words)) * 0.3 if q_words else 0.0
            score = sim + lexical_boost

            results.append({
                "id": row_dict["id"],
                "file": row_dict["file"],
                "section": row_dict["section"],
                "text": row_dict["text"],
                "score": round(score, 4),
                "modified_at": row_dict["modified_at"],
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

