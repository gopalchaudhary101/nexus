"""Internal RAG evaluation dataset.

A small curated set of questions with known ground truth (expected document,
expected keywords). Cases reference documents by filename stem so the dataset
is stable across re-runs of the synthetic generator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_doc: str          # filename stem of the source document
    expected_keywords: list[str]
    category: str = "rag"


def load_eval_dataset(path: str | Path) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text())
    return [EvalCase(id=c["id"], question=c["question"], expected_doc=c["expected_doc"],
                     expected_keywords=c["expected_keywords"],
                     category=c.get("category", "rag")) for c in raw["cases"]]
