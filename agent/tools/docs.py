"""Personal Documents search tool (RAG)."""

from typing import Any, Dict
from rag.store import search_doc_chunks


def search_my_docs(query: str) -> Dict[str, Any]:
    """Retrieve relevant chunks from your indexed personal documents with source names.
    
    Use when answering questions grounded in user files, PDFs, or notes.
    """
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

