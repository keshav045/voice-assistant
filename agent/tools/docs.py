"""Personal Documents search tool (RAG)."""

from typing import Any, Dict, Optional
from rag.store import search_doc_chunks


def search_my_docs(query: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve relevant chunks from your indexed personal documents with source names.
    
    Use when answering questions grounded in user files, PDFs, or notes.
    """
    try:
        chunks = search_doc_chunks(query=query, top_k=3, user_id=user_id)
    except TypeError:
        chunks = search_doc_chunks(query=query, top_k=3)
    if not chunks or chunks[0]["score"] < 0.1:
        return {
            "success": True,
            "count": 0,
            "chunks": [],
            "spoken": f"I checked your documents but found no relevant information about '{query}'.",
        }

    top = chunks[0]
    spoken = f"According to {top['file']} ({top['section']}): {top['text'][:220]}"
    return {
        "success": True,
        "count": len(chunks),
        "chunks": chunks,
        "spoken": spoken,
    }

