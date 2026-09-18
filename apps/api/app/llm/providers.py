"""Real LLM providers (OpenAI / Anthropic / Gemini) over HTTPS.

These are credential-gated integrations: they activate only when the
matching API key is present in the environment. They are deliberately thin
and raise explicit errors on failure — they never fall back to pretending
to be real output.
"""
from __future__ import annotations

import json

import httpx


class ProviderError(RuntimeError):
    pass


def _post(url: str, headers: dict, payload: dict, timeout: float = 60.0) -> dict:
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code >= 400:
            raise ProviderError(f"LLM provider HTTP {r.status_code}: {r.text[:300]}")
        return r.json()
    except httpx.HTTPError as e:
        raise ProviderError(f"LLM provider network error: {e}") from e


class OpenAIProvider:
    name = "openai"
    is_mock = False

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        payload: dict = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {self.api_key}"},
            payload,
        )
        return data["choices"][0]["message"]["content"]


class AnthropicProvider:
    name = "anthropic"
    is_mock = False

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5") -> None:
        self.api_key = api_key
        self.model = model

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        sys_prompt = system + ("\nRespond with valid JSON only." if json_mode else "")
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            {"model": self.model, "max_tokens": 1024, "system": sys_prompt,
             "messages": [{"role": "user", "content": user}]},
        )
        return "".join(block.get("text", "") for block in data.get("content", []))


class GeminiProvider:
    name = "gemini"
    is_mock = False

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        instruction = system + ("\nRespond with valid JSON only." if json_mode else "")
        data = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}",
            {},  # key goes in the query string for this API, not a header
            {
                "systemInstruction": {"parts": [{"text": instruction}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
            },
        )
        cand = data["candidates"][0]["content"]["parts"][0]["text"]
        return cand


def _parse_json_lenient(text: str) -> dict:
    """Parse a JSON object out of model output, tolerating code fences."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end > start:
        t = t[start:end + 1]
    return json.loads(t)


def chat_json(client, system: str, user: str) -> dict:
    raw = client.chat(system, user, json_mode=True)
    return _parse_json_lenient(raw)
