"""RAG quality metrics.

Definitions (kept simple and honest for the dataset size):
    retrieval_precision@1   top-1 retrieved chunk's document == expected doc
    retrieval_recall@k      expected doc present in top-k retrieved docs (k=5)
    citation_accuracy       answer cites the expected doc (when it answers)
    answer_correctness      answer contains >=1 expected keyword AND is not a
                            refusal ("couldn't find" / "not enough")
    latency                 wall-clock ms of retrieve+answer per case
All metrics are computed from actual runs; callers must surface "not yet
evaluated" instead of inventing numbers.
"""
from __future__ import annotations

REFUSAL_MARKERS = ("couldn't find", "could not find", "not enough",
                   "no information", "i don't have")


def _is_refusal(answer: str) -> bool:
    a = answer.lower()
    return any(m in a for m in REFUSAL_MARKERS)


def case_metrics(case: dict) -> dict:
    """case: {retrieved_docs:[...top5], top1_doc, answer, answer_sources:[...]}"""
    top1 = case.get("top1_doc") or ""
    retrieved = case.get("retrieved_docs") or []
    sources = case.get("answer_sources") or []
    answer = (case.get("answer") or "").lower()
    exp = case["expected_doc"]
    kws = [k.lower() for k in case["expected_keywords"]]

    prec1 = 1.0 if exp in top1 else 0.0
    recall5 = 1.0 if any(exp in d for d in retrieved) else 0.0
    cited = 1.0 if (sources and any(exp in s for s in sources) and not _is_refusal(answer)) else 0.0
    correct = 1.0 if (not _is_refusal(answer) and any(k in answer for k in kws)) else 0.0
    return {"precision_at_1": prec1, "recall_at_5": recall5,
            "citation_accuracy": cited, "answer_correctness": correct,
            "latency_ms": round(case.get("latency_ms", 0.0), 1)}


def compute_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"evaluated": False,
                "message": "Not yet evaluated. Run an evaluation against the "
                           "RAG pipeline to produce real metrics."}
    n = len(rows)
    agg = {}
    for key in ("precision_at_1", "recall_at_5", "citation_accuracy", "answer_correctness"):
        agg[key] = round(sum(r[key] for r in rows) / n, 3)
    lats = sorted(r["latency_ms"] for r in rows)
    agg["latency_ms_avg"] = round(sum(lats) / n, 1)
    agg["latency_ms_p95"] = round(lats[min(n - 1, int(0.95 * (n - 1)))], 1)
    return {"evaluated": True, "n_cases": n, "metrics": agg, "rows": rows}
