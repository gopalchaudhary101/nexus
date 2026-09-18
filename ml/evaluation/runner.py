"""Evaluation runner: glue between the dataset and a live RAG pipeline.

`retrieve_and_answer(question) -> {top1_doc, retrieved_docs, answer,
answer_sources, latency_ms}` is supplied by the application layer; the
runner stays transport-agnostic so it can be used by tests too.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .dataset import EvalCase, load_eval_dataset
from .metrics import case_metrics, compute_metrics


@dataclass
class EvalRunner:
    cases: list[EvalCase]
    retrieve_and_answer: Callable[[str], dict]

    @classmethod
    def from_dataset_file(cls, path, retrieve_and_answer: Callable[[str], dict]) -> EvalRunner:
        return cls(load_eval_dataset(path), retrieve_and_answer)

    def run(self) -> dict:
        rows = []
        for case in self.cases:
            t0 = time.perf_counter()
            try:
                res = self.retrieve_and_answer(case.question)
                latency = (time.perf_counter() - t0) * 1000
                res = {**res, "latency_ms": res.get("latency_ms", latency)}
            except Exception as e:  # noqa: BLE001 - eval must record failures, not crash
                res = {"top1_doc": "", "retrieved_docs": [], "answer": f"ERROR: {e}",
                       "answer_sources": [], "latency_ms": (time.perf_counter() - t0) * 1000}
            row = {
                "id": case.id,
                "question": case.question,
                "expected_doc": case.expected_doc,
                "expected_keywords": case.expected_keywords,
                "retrieved_docs": res.get("retrieved_docs", []),
                "top1_doc": res.get("top1_doc", ""),
                "answer": res.get("answer", ""),
                "answer_sources": res.get("answer_sources", []),
                "latency_ms": res.get("latency_ms", 0.0),
            }
            row.update(case_metrics(row))
            rows.append(row)
        report = compute_metrics(rows)
        report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return report
