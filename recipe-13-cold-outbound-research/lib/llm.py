from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from anthropic import Anthropic
from openai import OpenAI

from lib.secrets import vault_credential_strict


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMClient:
    """LLM wrapper that delegates to the official OpenAI / Anthropic SDKs.

    The injectable ``client`` parameter is forwarded to both SDKs as their
    ``http_client``, so tests can wire an ``httpx.MockTransport`` exactly the
    same way they did with the previous raw-httpx implementation.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
        self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")
        self.anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
        self._http = client

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
        key = vault_credential_strict("OPENAI_API_KEY")
        client = OpenAI(api_key=key, http_client=self._http, timeout=60.0)
        resp = client.chat.completions.create(
            model=self.openai_model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
        return LLMResult(text=text, provider="openai", model=self.openai_model)

    def _anthropic(self, system: str, user: str) -> LLMResult:
        key = vault_credential_strict("ANTHROPIC_API_KEY")
        client = Anthropic(api_key=key, http_client=self._http, timeout=60.0)
        resp = client.messages.create(
            model=self.anthropic_model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return LLMResult(text="".join(parts), provider="anthropic", model=self.anthropic_model)
