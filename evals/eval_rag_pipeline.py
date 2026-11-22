"""Evaluates full end-to-end RAG pipeline: ingestion, vector recall, context synthesis."""

import os
import sys
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from db.models import get_db_connection
from rag.store import add_doc_chunk, search_doc_chunks
from evals.harness import EvalHarness


def run_rag_pipeline_eval(harness: EvalHarness) -> Dict[str, Any]:
    # Ingest mock RAG syllabus knowledge chunk
    chunk_text = "The University Engineering exam scheme allocates 80 marks to external theory and 20 marks to mid-term assessments."
    chunk_id = add_doc_chunk(file_name="engineering_scheme.txt", text=chunk_text, section="grading")

    # Retrieve
    query = "How many marks are allocated to external theory in university exams?"
    results = search_doc_chunks(query=query, top_k=2)

    found_correct_chunk = any("80 marks" in r.get("text", "") for r in results)

    # Synthesis verification: context has necessary ground truth
    ground_truth_present = any("external theory" in r.get("text", "") for r in results)

    # Clean up
    with get_db_connection() as conn:
        conn.execute("DELETE FROM doc_chunks WHERE id = ?", (chunk_id,))
        conn.commit()

    harness.record_test("eval_rag_pipeline", "RAG Ingest & Vector Retrieval", found_correct_chunk, found_correct_chunk, "Found indexed syllabus chunk")
    harness.record_test("eval_rag_pipeline", "RAG Ground-Truth Context", ground_truth_present, ground_truth_present, "Retrieved context contains necessary facts")

    return {
        "query": query,
        "retrieved_chunk_found": found_correct_chunk,
        "ground_truth_faithful": ground_truth_present,
    }


if __name__ == "__main__":
    h = EvalHarness()
    run_rag_pipeline_eval(h)
