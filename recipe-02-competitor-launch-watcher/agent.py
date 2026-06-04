"""Competitor launch watcher — fetch pages, diff titles, LLM summary."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from integrations.competitors import PageSnapshot, fetch_competitors
from lib.config import competitor_list, titles_cache_path
from lib.llm import LLMClient
from lib.store import TitleCache

SUMMARY_SYSTEM = """You are a competitive intelligence analyst.
Given new vs previous page titles from competitor blogs/changelogs,
identify genuinely new launches or features. Return JSON:
{"summary": "2-3 sentence briefing", "changes": [{"competitor": "...", "new_titles": ["..."]}]}"""


@dataclass
class RunResult:
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


def run_watch(*, dry_run: bool = False, llm: LLMClient | None = None, http: httpx.Client | None = None) -> RunResult:
    competitors = competitor_list()
    cache = TitleCache(titles_cache_path())
    snapshots = fetch_competitors(competitors, client=http)

    changes: list[dict[str, object]] = []
    for snap in snapshots:
        previous = cache.get(snap.url) or []
        new_titles = [t for t in snap.titles if t not in previous]
        if new_titles:
            changes.append({"competitor": snap.name, "new_titles": new_titles, "previous": previous})
        cache.set(snap.url, snap.titles)

    if dry_run:
        digest = _format_changes(changes, summary="Dry run — LLM skipped.")
        return RunResult(
            fetched=len(snapshots),
            new=len(changes),
            kept=len(changes),
            digest=digest,
            mail_sent=False,
            dry_run=True,
        )

    if not changes:
        cache.flush()
        return RunResult(
            fetched=len(snapshots),
            new=0,
            kept=0,
            digest="No new competitor launches detected.",
            mail_sent=False,
            dry_run=False,
        )

    client = llm or LLMClient(client=http)
    payload = str(changes)
    result = client.complete_json(SUMMARY_SYSTEM, payload)
    summary = str(result.get("summary") or "Competitor changes detected.")
    digest = _format_changes(changes, summary=summary)

    cache.flush()
    return RunResult(
        fetched=len(snapshots),
        new=len(changes),
        kept=len(changes),
        digest=digest,
        mail_sent=False,
        dry_run=False,
    )


def _format_changes(changes: list[dict[str, object]], *, summary: str) -> str:
    lines = [summary, ""]
    for change in changes:
        lines.append(f"## {change['competitor']}")
        for title in change.get("new_titles", []):
            lines.append(f"- {title}")
        lines.append("")
    return "\n".join(lines).strip()
