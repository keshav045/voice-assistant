"""Evaluates dense document retrieval and semantic memory precision."""

import os
import sys
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from db.models import get_db_connection, db_add_fact, db_list_facts, db_forget_fact
from rag.store import add_doc_chunk, search_doc_chunks
from evals.metric_registry import compute_hit_at_k, compute_mrr, compute_ndcg_at_k
from evals.harness import EvalHarness


def run_retriever_eval(harness: EvalHarness) -> Dict[str, Any]:
    test_docs = [
        {"file": "wifi_guide.txt", "text": "The guest Wi-Fi network SSID is OfficeGuest and the password is securePass2026.", "queries": ["What is the guest wifi password?", "How do I connect to wifi?"]},
        {"file": "q4_roadmap.txt", "text": "Project Nexus aims to launch LiveKit real-time voice streaming and Gmail OAuth in Q4.", "queries": ["When is Nexus launching voice streaming?", "What are the Q4 goals?"]},
        {"file": "leave_policy.pdf", "text": "Employees receive 24 days of paid time off per calendar year and 10 public holidays.", "queries": ["How many PTO days do we get?", "What is the annual leave policy?"]},
        {"file": "deployment.md", "text": "Deployments to Vercel require setting OPENAI_API_KEY and LIVEKIT credentials in environment variables.", "queries": ["How to deploy on Vercel?", "What env vars are needed for Vercel?"]},
    ]

    chunk_ids = []
    for d in test_docs:
        cid = add_doc_chunk(file_name=d["file"], text=d["text"], section="general")
        chunk_ids.append(cid)

    hits_1 = []
    hits_3 = []
    ranks = []

    for d in test_docs:
        for q in d["queries"]:
            res = search_doc_chunks(query=q, top_k=3)
            files = [r["file"] for r in res]
            hit_1 = compute_hit_at_k(files, d["file"], k=1)
            hit_3 = compute_hit_at_k(files, d["file"], k=3)
            rank = (files.index(d["file"]) + 1) if d["file"] in files else None

            hits_1.append(hit_1)
            hits_3.append(hit_3)
            ranks.append(rank)

    # Clean up test chunks
    with get_db_connection() as conn:
        for cid in chunk_ids:
            conn.execute("DELETE FROM doc_chunks WHERE id = ?", (cid,))
        conn.commit()

    hit_1_pct = round((sum(hits_1) / len(hits_1)) * 100, 1)
    hit_3_pct = round((sum(hits_3) / len(hits_3)) * 100, 1)
    mrr_score = round(compute_mrr(ranks), 3)

    # Semantic memory test
    fact_id = db_add_fact("Student favorite subject is Machine Learning", category="academic")
    memory_facts = db_list_facts()
    memory_ok = any("Machine Learning" in f.get("fact", "") for f in memory_facts)
    db_forget_fact("Machine Learning")

    harness.record_test("eval_retriever", "Document Hit@1", hit_1_pct >= 80.0, hit_1_pct, f"{hit_1_pct}% top-1 retrieval")
    harness.record_test("eval_retriever", "Document Hit@3", hit_3_pct >= 80.0, hit_3_pct, f"{hit_3_pct}% top-3 retrieval")
    harness.record_test("eval_retriever", "MRR Score", mrr_score >= 0.75, mrr_score, f"MRR: {mrr_score}")
    harness.record_test("eval_retriever", "Semantic Memory Fact", memory_ok, memory_ok, "Recalled saved memory fact")

    return {
        "hit_at_1_pct": hit_1_pct,
        "hit_at_3_pct": hit_3_pct,
        "mrr": mrr_score,
        "memory_recalled": memory_ok,
    }


if __name__ == "__main__":
    h = EvalHarness()
    run_retriever_eval(h)
