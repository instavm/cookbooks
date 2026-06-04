"""Podcast prep — transcript to show notes + optional Cartesia stub."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from integrations.cartesia import synthesize_intro
from lib.config import notes_path
from lib.llm import LLMClient

SHOW_NOTES_SYSTEM = """You prepare podcast show notes from a transcript.
Return JSON only:
{
  "episode_title": "string",
  "summary": "2-3 sentences",
  "chapters": [{"timestamp": "00:00", "title": "..."}],
  "key_quotes": ["..."],
  "guest_bio": "string or null",
  "social_posts": ["tweet-length promo"],
  "intro_script": "30-second host intro script for TTS"
}"""


@dataclass
class PrepResult:
    show_notes: dict[str, Any]
    tts_stub: bool
    tts_bytes: int
    dry_run: bool


def prepare_episode(
    transcript: str,
    *,
    episode_title: str = "",
    with_tts: bool = False,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> PrepResult:
    if dry_run:
        notes = {
            "episode_title": episode_title or "Dry run episode",
            "summary": "Dry run — LLM skipped.",
            "chapters": [{"timestamp": "00:00", "title": "Intro"}],
            "key_quotes": [],
            "guest_bio": None,
            "social_posts": [],
            "intro_script": "Welcome to the show.",
        }
        _persist_notes(notes)
        return PrepResult(show_notes=notes, tts_stub=True, tts_bytes=0, dry_run=True)

    client = llm or LLMClient(client=http)
    user = f"Episode title hint: {episode_title or 'Unknown'}\n\nTranscript:\n{transcript[:14000]}"
    notes = client.complete_json(SHOW_NOTES_SYSTEM, user)
    _persist_notes(notes)

    tts_stub = True
    tts_bytes = 0
    if with_tts:
        intro = str(notes.get("intro_script") or notes.get("summary") or "")
        tts = synthesize_intro(intro, client=http)
        tts_stub = tts.stub
        tts_bytes = len(tts.audio_bytes)

    return PrepResult(show_notes=notes, tts_stub=tts_stub, tts_bytes=tts_bytes, dry_run=False)


def load_notes() -> dict[str, Any] | None:
    path = notes_path()
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _persist_notes(notes: dict[str, Any]) -> None:
    path = notes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notes, indent=2), encoding="utf-8")
