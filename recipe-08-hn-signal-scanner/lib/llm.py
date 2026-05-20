from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from lib.secrets import vault_credential

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
        self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")
        self.anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
        self._client = client or httpx.Client(timeout=60.0)

    def complete(self, system: str, user: str) -> LLMResult:
        if self.provider == "anthropic":
            return self._anthropic(system, user)
        return self._openai(system, user)

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        text = self.complete(system, user + "\nRespond with valid JSON only.").text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].removesuffix("```").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    def _openai(self, system: str, user: str) -> LLMResult:
        key = vault_credential("OPENAI_API_KEY")
        resp = self._client.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": self.openai_model,
                "temperature": 0.2,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return LLMResult(text=text, provider="openai", model=self.openai_model)

    def _anthropic(self, system: str, user: str) -> LLMResult:
        key = vault_credential("ANTHROPIC_API_KEY")
        resp = self._client.post(
            ANTHROPIC_URL,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={
                "model": self.anthropic_model,
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        parts = [b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text"]
        return LLMResult(text="".join(parts), provider="anthropic", model=self.anthropic_model)
