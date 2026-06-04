"""Voice transcript → LLM roadmap items → Notion append."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from integrations.notion import append_roadmap_items
from lib.config import intake_path
from lib.llm import LLMClient

ROADMAP_SYSTEM = """Extract product roadmap items from a voice transcript.
Return JSON: {"items": [{"title": "...", "priority": "High|Medium|Low", "rationale": "one line"}]}
Return at most 5 items. Only include clear product intents."""


@dataclass
class TranscriptResult:
    items: list[dict[str, Any]]
    notion_appended: int
    dry_run: bool


def process_transcript(
    transcript: str,
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> TranscriptResult:
    text = transcript.strip()
    if not text:
        return TranscriptResult(items=[], notion_appended=0, dry_run=dry_run)

    if dry_run:
        items = [{"title": "Dry-run placeholder", "priority": "Medium", "rationale": "LLM skipped"}]
        _record_intake(text, items, dry_run=True)
        return TranscriptResult(items=items, notion_appended=0, dry_run=True)

    client = llm or LLMClient(client=http)
    parsed: dict[str, Any] = client.complete_json(ROADMAP_SYSTEM, text)
    items = list(parsed.get("items") or [])
    notion = append_roadmap_items(items, dry_run=False, client=http)
    _record_intake(text, items, dry_run=False)
    return TranscriptResult(items=items, notion_appended=notion.appended, dry_run=False)


def _record_intake(transcript: str, items: list[dict[str, Any]], *, dry_run: bool) -> None:
    path = intake_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    history: list[dict[str, Any]] = []
    if path.exists():
        history = json.loads(path.read_text(encoding="utf-8"))
    history.append({"transcript": transcript[:500], "items": items, "dry_run": dry_run})
    path.write_text(json.dumps(history[-50:], indent=2), encoding="utf-8")
