"""Deterministic LLM replay via InstaVM cassette."""

from __future__ import annotations

from dataclasses import dataclass

from lib.replay import replay_chat_completion


@dataclass
class ReplayResult:
    content: str
    deterministic: bool = True


def run_replay() -> ReplayResult:
    content = replay_chat_completion()
    return ReplayResult(content=content, deterministic=True)
