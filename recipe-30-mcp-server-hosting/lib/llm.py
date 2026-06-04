"""LLM stub — not used by this recipe; included for cookbook layout consistency."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMClient:
    def complete(self, system: str, user: str) -> LLMResult:
        raise NotImplementedError("This recipe does not call an LLM")

    def complete_json(self, system: str, user: str) -> dict:
        raise NotImplementedError("This recipe does not call an LLM")
