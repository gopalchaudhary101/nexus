"""Deterministic mock LLM for offline development and demos.

Mock mode is a *declared* mode, not a pretence:
  - RAG answers in mock mode come from the extractive, source-grounded
    pipeline (rag/answers.py) — citations and refusals are real.
  - Agent planning uses the deterministic rule planner (agents/planner.py).
  - This class exists so provider-shaped code paths stay testable.
"""
from __future__ import annotations

import json


class MockLLM:
    name = "mock-llm-v1"
    is_mock = True

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        if json_mode:
            return json.dumps({
                "answer": "Mock mode: the deterministic local pipeline handled this request. "
                          "Configure a real provider (NEXUS_LLM_PROVIDER) for generative text.",
                "confidence": 0.0,
                "sources": [],
            })
        return ("Mock LLM (deterministic local mode). No external API calls are made in this "
                "deployment; answers are produced by the rule/extractive pipelines.")
