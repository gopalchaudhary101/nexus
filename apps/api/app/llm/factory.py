"""Provider selection (env-driven). Cached singletons per process."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from ..core.config import get_settings
from .mock import MockLLM
from .providers import AnthropicProvider, GeminiProvider, OpenAIProvider


@lru_cache
def get_llm():
    s = get_settings()
    if s.llm_provider == "openai" and s.openai_api_key:
        return OpenAIProvider(s.openai_api_key, s.llm_model)
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider(s.anthropic_api_key, s.llm_model)
    if s.llm_provider == "gemini" and s.gemini_api_key:
        return GeminiProvider(s.gemini_api_key, s.llm_model)
    if s.llm_provider != "mock":
        # Configured a real provider but no key: be explicit, don't pretend.
        raise RuntimeError(
            f"NEXUS_LLM_PROVIDER={s.llm_provider} but no API key is set. "
            "Set the key or use mock mode."
        )
    return MockLLM()


@lru_cache
def get_embedder():
    s = get_settings()
    if s.embed_provider == "openai" and s.openai_api_key:
        return OpenAIEmbedder(s.openai_api_key, s.embed_model)
    from ml.embeddings import HashEmbedder
    return HashEmbedder(dim=384)


class OpenAIEmbedder:
    """OpenAI embeddings via HTTP (credential-gated integration)."""

    name = "openai-embeddings"

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self.api_key = api_key
        self.model = model
        self.dim = 1536

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        import httpx
        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=60.0,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Embedding provider HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()["data"]
        data.sort(key=lambda d: d["index"])
        return np.array([d["embedding"] for d in data], dtype=np.float32)

    def embed(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]
