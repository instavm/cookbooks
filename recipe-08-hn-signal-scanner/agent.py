"""HN signal scanner — fetch, dedup, LLM filter, Mailtrap digest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from integrations.hn import Story, fetch_stories
from lib.config import DIGEST_TO, HN_QUERY, MAX_STORIES, seen_path
from lib.llm import LLMClient
from lib.mail import send_email
from lib.store import JsonStore

FILTER_SYSTEM = """You filter Hacker News stories for a technical founder audience.
Return JSON: {"keep": [{"id": "...", "reason": "one line"}], "summary": "2-3 sentence digest"}
Keep at most 8 high-signal stories about AI agents, infra, devtools, or startups."""


@dataclass
class RunResult:
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


def run_scan(*, dry_run: bool = False, llm: LLMClient | None = None, http: httpx.Client | None = None) -> RunResult:
    store = JsonStore(seen_path())
    stories = fetch_stories(HN_QUERY, limit=MAX_STORIES, client=http)
    new_stories = [s for s in stories if not store.seen(s.id)]

    if not new_stories:
        return RunResult(fetched=len(stories), new=0, kept=0, digest="No new stories.", mail_sent=False, dry_run=dry_run)

    if dry_run:
        digest = _format_digest(new_stories[:5], summary="Dry run — LLM skipped.")
        return RunResult(fetched=len(stories), new=len(new_stories), kept=min(5, len(new_stories)), digest=digest, mail_sent=False, dry_run=True)

    client = llm or LLMClient(client=http)
    payload = [{"id": s.id, "title": s.title, "url": s.url, "points": s.points} for s in new_stories]
    filtered: dict[str, Any] = client.complete_json(FILTER_SYSTEM, str(payload))
    keep_items = filtered.get("keep") or []
    summary = str(filtered.get("summary") or "")
    kept_ids = {str(item.get("id")) for item in keep_items if item.get("id")}
    kept_stories = [s for s in new_stories if s.id in kept_ids] or new_stories[:5]
    digest = _format_digest(kept_stories, summary=summary)

    store.mark_many(s.id for s in new_stories)
    store.flush()

    mail = send_email(to=DIGEST_TO, subject="HN Signal Digest", body=digest, dry_run=False)
    return RunResult(
        fetched=len(stories),
        new=len(new_stories),
        kept=len(kept_stories),
        digest=digest,
        mail_sent=mail.sent,
        dry_run=False,
    )


def _format_digest(stories: list[Story], *, summary: str) -> str:
    lines = [summary, "", "Stories:"]
    for s in stories:
        lines.append(f"- {s.title} ({s.points} pts)\n  {s.url}")
    return "\n".join(lines)
