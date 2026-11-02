"""RAG package."""
from rag.store import add_doc_chunk, search_doc_chunks
from rag.ingest import ingest_file, ingest_directory

__all__ = ["add_doc_chunk", "search_doc_chunks", "ingest_file", "ingest_directory"]

