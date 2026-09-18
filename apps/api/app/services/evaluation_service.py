"""RAG evaluation runner service (shared by API + seed script)."""
from __future__ import annotations

import json
import time
import uuid

from sqlalchemy.orm import Session

from ..core.config import ROOT
from ..db.models import RagEvalResult
from ..llm.factory import get_embedder, get_llm
from ..rag.answers import answer_question
from ..rag.retriever import HybridRetriever


def run_rag_evaluation(db: Session, user_id: str) -> dict:
    from ml.evaluation import EvalRunner

    dataset_path = ROOT / "data" / "demo" / "eval_set.json"
    if not dataset_path.exists():
        return {"error": "Evaluation dataset not found (run scripts/generate_demo_data.py)."}
    retriever = HybridRetriever(get_embedder())
    llm = get_llm()

    def retrieve_and_answer(question: str) -> dict:
        t0 = time.perf_counter()
        hits = retriever.search(db, user_id, question, top_k=5)
        ga = answer_question(question, hits, llm=llm)
        return {
            "top1_doc": hits[0].document_name if hits else "",
            "retrieved_docs": [h.document_name for h in hits[:5]],
            "answer": ga.answer,
            "answer_sources": [s["document_name"] for s in ga.sources],
            "latency_ms": (time.perf_counter() - t0) * 1000,
        }

    runner = EvalRunner.from_dataset_file(dataset_path, retrieve_and_answer)
    report = runner.run()
    run_id = f"EVAL-{uuid.uuid4().hex[:8]}"
    for row in report.get("rows", []):
        db.add(RagEvalResult(
            user_id=user_id, run_id=run_id, question=row["question"],
            expected_doc=row["expected_doc"],
            retrieved_docs_json=json.dumps(row["retrieved_docs"]),
            top1_doc=row["top1_doc"], answer=row["answer"][:2000],
            answer_sources_json=json.dumps(row["answer_sources"]),
            precision_at_1=row["precision_at_1"], recall_at_5=row["recall_at_5"],
            citation_accuracy=row["citation_accuracy"],
            answer_correctness=row["answer_correctness"], latency_ms=row["latency_ms"],
        ))
    db.commit()
    return report
