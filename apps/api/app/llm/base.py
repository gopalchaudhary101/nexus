"""LLM/embedding abstractions. The rest of the app only depends on these
two protocols, so providers are swappable via environment configuration."""
from __future__ import annotations

from typing import Protocol

import numpy as np


class LLMClient(Protocol):
    name: str
    is_mock: bool

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:  # noqa: D401
        """Return the model's text (or JSON string when json_mode)."""
        ...


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, text: str) -> np.ndarray: ...

    def embed_batch(self, texts: list[str]) -> np.ndarray: ...
