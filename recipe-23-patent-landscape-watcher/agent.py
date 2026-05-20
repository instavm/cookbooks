"""Patent landscape watcher — Exa + Firecrawl search, dedup store, LLM digest, Mailtrap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from integrations.exa import PatentHit, search_patents
from integrations.firecrawl import CompetitorHit, search_competitors
from lib.config import DIGEST_TO, PATENT_QUERY, seen_path
from lib.llm import LLMClient
from lib.mail import send_email
from lib.store import JsonStore

DIGEST_SYSTEM = """You summarize patent and competitive intelligence for a product team.
Return JSON: {"summary": "2-3 sentences", "highlights": [{"title": "...", "why": "one line"}]}
Highlight at most 6 new items."""


@dataclass
class RunResult:
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


def run_watch(*, dry_run: bool = False, llm: LLMClient | None = None, http: httpx.Client | None = None) -> RunResult:
    store = JsonStore(seen_path())
    patents = search_patents(PATENT_QUERY, client=http)
    competitors = search_competitors(PATENT_QUERY, client=http)
    combined: list[PatentHit | CompetitorHit] = [*patents, *competitors]
    new_hits = [h for h in combined if not store.seen(h.id)]

    if not new_hits:
        return RunResult(fetched=len(combined), new=0, kept=0, digest="No new patent or competitor signals.", mail_sent=False, dry_run=dry_run)

    if dry_run:
        digest = _format_digest(new_hits[:5], summary="Dry run — LLM and Mailtrap skipped.")
        return RunResult(
            fetched=len(combined),
            new=len(new_hits),
            kept=min(5, len(new_hits)),
            digest=digest,
            mail_sent=False,
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    payload = [{"id": h.id, "title": h.title, "url": h.url, "source": h.source} for h in new_hits]
    filtered: dict[str, Any] = client.complete_json(DIGEST_SYSTEM, str(payload))
    highlights = filtered.get("highlights") or []
    summary = str(filtered.get("summary") or "")
    highlight_ids = {str(item.get("title")) for item in highlights}
    kept = [h for h in new_hits if h.title in highlight_ids] or new_hits[:5]
    digest = _format_digest(kept, summary=summary)

    store.mark_many(h.id for h in new_hits)
    store.flush()

    mail = send_email(to=DIGEST_TO, subject="Patent Landscape Digest", body=digest, dry_run=False)
    return RunResult(
        fetched=len(combined),
        new=len(new_hits),
        kept=len(kept),
        digest=digest,
        mail_sent=mail.sent,
        dry_run=False,
    )


def _format_digest(hits: list[PatentHit | CompetitorHit], *, summary: str) -> str:
    lines = [summary, "", "Signals:"]
    for h in hits:
        lines.append(f"- [{h.source}] {h.title}\n  {h.url}\n  {h.snippet[:120]}...")
    return "\n".join(lines)
