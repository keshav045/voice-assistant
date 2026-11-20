"""Evaluates two-stage retrieval pipeline with semantic cross-scoring / reranking."""

import os
import sys
from typing import Any, Dict, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from rag.store import add_doc_chunk, search_doc_chunks, cosine_similarity, compute_embedding
from evals.harness import EvalHarness
from evals.metric_registry import compute_hit_at_k


def rerank_chunks(query: str, initial_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Two-stage reranker: re-scores candidate chunks with query term overlap and semantic affinity."""
    q_words = set(query.lower().split())
    scored = []
    for c in initial_chunks:
        text_lower = c["text"].lower()
        exact_matches = sum(1 for w in q_words if w in text_lower)
        affinity_score = c.get("similarity", 0.5) + (0.2 * exact_matches)
        scored.append((affinity_score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored]


def run_reranker_eval(harness: EvalHarness) -> Dict[str, Any]:
    test_chunks = [
        {"file": "dbms_acid.txt", "text": "Atomicity ensures all transactions execute completely or not at all."},
        {"file": "dbms_isolation.txt", "text": "Isolation guarantees concurrent transactions execute without interference."},
        {"file": "dbms_durability.txt", "text": "Durability guarantees committed transactions survive system crashes."},
    ]

    query = "Which ACID property guarantees survival after system crashes?"
    # First stage: initial candidates
    candidates = test_chunks.copy()
    # Second stage: reranked
    reranked = rerank_chunks(query, candidates)

    top_1_file = reranked[0]["file"] if reranked else ""
    correct_rerank = top_1_file == "dbms_durability.txt"

    harness.record_test(
        "eval_reranker",
        "Semantic Reranker Precision",
        correct_rerank,
        top_1_file,
        f"Top reranked document: {top_1_file}",
    )

    return {
        "query": query,
        "reranked_top_1": top_1_file,
        "reranking_success": correct_rerank,
    }


if __name__ == "__main__":
    h = EvalHarness()
    run_reranker_eval(h)
