"""Vector store wrapper for Personal Documents (RAG)."""

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from db.models import get_db_connection

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "can", "could", "did", "do", "does", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it", "its", "itself", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so", "some",
    "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with", "would", "you", "your"
}


def _tokenize(text: str) -> List[str]:
    """Tokenize and normalize text into clean lower-case terms."""
    normalized = text.lower().replace("-", " ")
    return re.findall(r"[a-zA-Z0-9]+", normalized)


def _compute_local_hash_embedding(text: str) -> List[float]:
    """Deterministic cross-process 128-dim lexical hash embedding."""
    tokens = _tokenize(text)
    dim = 128
    vec = [0.0] * dim
    for i, w in enumerate(tokens):
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16) % dim
        weight = 0.2 if w in STOP_WORDS else 1.0
        vec[h] += weight / (1.0 + math.log(i + 1))
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def compute_embedding(text: str) -> List[float]:
    """Compute vector embedding using OpenAI or deterministic cross-process fallback."""
    api_key = os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY).strip()
    if api_key and api_key.startswith("sk-"):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            res = client.embeddings.create(input=text[:8000], model="text-embedding-3-small")
            return res.data[0].embedding
        except Exception:
            pass

    return _compute_local_hash_embedding(text)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1)) or 1.0
    norm2 = math.sqrt(sum(b * b for b in v2)) or 1.0
    return dot / (norm1 * norm2)


def add_doc_chunk(
    file_name: str,
    text: str,
    section: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """Store a document chunk with embedding in doc_chunks."""
    chunk_id = f"chunk-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    eff_uid = (user_id or "guest").strip() or "guest"
    emb = compute_embedding(text)
    emb_json = json.dumps(emb)

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO doc_chunks (id, user_id, file, section, text, embedding, modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, eff_uid, file_name, section or "", text, emb_json, now),
        )
        conn.commit()
    return chunk_id


def delete_doc_chunks_for_file(file_name: str, user_id: Optional[str] = None) -> int:
    """Remove existing chunks for a filename before re-ingesting to avoid duplicates."""
    with get_db_connection() as conn:
        if user_id:
            cur = conn.execute("DELETE FROM doc_chunks WHERE file = ? AND user_id = ?", (file_name, user_id))
        else:
            cur = conn.execute("DELETE FROM doc_chunks WHERE file = ?", (file_name,))
        conn.commit()
        return cur.rowcount


def search_doc_chunks(
    query: str,
    top_k: int = 3,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search document chunks by semantic cosine similarity with dimension alignment and lexical rerank."""
    query_emb = compute_embedding(query)
    local_query_emb = _compute_local_hash_embedding(query)
    results = []

    with get_db_connection() as conn:
        if user_id:
            cur = conn.execute(
                "SELECT id, file, section, text, embedding, modified_at FROM doc_chunks WHERE user_id = ? OR user_id = 'guest'",
                (user_id,),
            )
        else:
            cur = conn.execute("SELECT id, file, section, text, embedding, modified_at FROM doc_chunks")
        rows = cur.fetchall()

    q_tokens = [t for t in _tokenize(query) if t not in STOP_WORDS]

    for row in rows:
        row_dict = dict(row)
        try:
            emb = json.loads(row_dict["embedding"]) if row_dict.get("embedding") else []
            if len(emb) == len(query_emb):
                sim = cosine_similarity(query_emb, emb)
            elif len(emb) == len(local_query_emb):
                sim = cosine_similarity(local_query_emb, emb)
            else:
                # Re-embed chunk text on-the-fly with active local model if dimensions differ
                sim = cosine_similarity(local_query_emb, _compute_local_hash_embedding(row_dict["text"]))

            # Lexical boost
            text_lower = row_dict["text"].lower()
            text_tokens = set(_tokenize(row_dict["text"]))
            if q_tokens:
                keyword_matches = sum(
                    1 for w in q_tokens
                    if w in text_tokens or w in text_lower or (w == "wifi" and "wi-fi" in text_lower)
                )
                lexical_boost = (keyword_matches / len(q_tokens)) * 0.45
            else:
                lexical_boost = 0.0

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

