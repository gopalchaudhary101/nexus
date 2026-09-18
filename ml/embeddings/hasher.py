"""Deterministic local embedding model (hashing trick).

Purpose
    Provide real vector search with zero external dependencies so that RAG,
    hybrid retrieval and the full pipeline are runnable offline (mock mode).

Design
    - unigram + bigram features hashed into `dim` buckets
    - signed double-hashing to reduce collision bias
    - sqrt term-frequency compression, L2 normalised
    - fully deterministic: same text -> same vector, across processes

Limitations (stated honestly)
    - This is a LEXICAL embedding, not a trained semantic model. It retrieves
      near-lexical matches well; paraphrases are out of scope.
    - Production path: configure NEXUS_EMBED_PROVIDER=openai (or Gemini) and
      the retriever is unchanged (same `embed(text) -> vector` contract).
"""
from __future__ import annotations

import hashlib
import re

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    """Offline deterministic embedder. See module docstring."""

    name = "hash-embedder-v1"

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        toks = _TOKEN_RE.findall((text or "").lower())
        bigrams = [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        return toks + bigrams

    def embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for feat in self._features(text):
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        vec = np.sign(vec) * np.sqrt(np.abs(vec))
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self.embed(t) for t in texts])
