"""Document Ingestion Pipeline (PDF, Markdown, Text)."""

import os
from typing import List, Optional
from rag.store import add_doc_chunk, delete_doc_chunks_for_file


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks safely (guards against overlap >= chunk_size)."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")
    safe_overlap = max(0, min(overlap, chunk_size - 1))
    step = chunk_size - safe_overlap

    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk.strip())
        i += step
    return chunks


def ingest_file(file_path: str, user_id: Optional[str] = None) -> int:
    """Ingest a text, Markdown, or PDF file into the vector store (replaces prior chunks for same file)."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = os.path.basename(file_path)
    text = ""

    if file_path.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages_text)
        except Exception:
            # Fallback simple binary text extraction
            with open(file_path, "rb") as f:
                raw = f.read()
            text = "".join(chr(b) for b in raw if 32 <= b <= 126 or b in (10, 13))
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

    delete_doc_chunks_for_file(filename, user_id=user_id)
    chunks = chunk_text(text)
    for idx, c in enumerate(chunks):
        add_doc_chunk(file_name=filename, text=c, section=f"Part {idx + 1}", user_id=user_id)

    return len(chunks)


def ingest_directory(dir_path: str) -> int:
    """Ingest all supported documents in a folder."""
    if not os.path.exists(dir_path):
        return 0

    count = 0
    for root, _, files in os.walk(dir_path):
        for f in files:
            if f.endswith((".txt", ".md", ".pdf")):
                path = os.path.join(root, f)
                try:
                    count += ingest_file(path)
                except Exception:
                    continue
    return count

