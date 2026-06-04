"""Substack distribution — scrape, LLM rewrite for LinkedIn/X, preview HTML."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from integrations.firecrawl import ScrapedPost, scrape_url
from lib.config import drafts_path, ledger_path, preview_path
from lib.llm import LLMClient
from lib.store import JsonStore

REWRITE_SYSTEM = """You rewrite blog posts for social distribution.
Return JSON: {"linkedin": "LinkedIn post text", "x_thread": "X thread with tweets separated by blank lines"}
LinkedIn: professional tone, 3 short paragraphs, end with a question.
X: thread of 3 tweets, each under 280 characters."""


@dataclass
class PublishResult:
    url: str
    title: str
    linkedin: str
    x_thread: str
    already_distributed: bool
    dry_run: bool


def run_publish(
    url: str,
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> PublishResult:
    ledger = JsonStore(ledger_path())
    if ledger.seen(url):
        return PublishResult(
            url=url,
            title="",
            linkedin="",
            x_thread="",
            already_distributed=True,
            dry_run=dry_run,
        )

    post = scrape_url(url, client=http)

    if dry_run:
        linkedin, x_thread = _dry_run_variants(post)
    else:
        client = llm or LLMClient(client=http)
        parsed: dict[str, Any] = client.complete_json(REWRITE_SYSTEM, post.markdown[:3000])
        linkedin = str(parsed.get("linkedin") or "")
        x_thread = str(parsed.get("x_thread") or "")

    html = _preview_html(post.title, post.url, linkedin, x_thread)
    preview_path().parent.mkdir(parents=True, exist_ok=True)
    preview_path().write_text(html, encoding="utf-8")

    drafts_path().write_text(
        json.dumps({"linkedin": linkedin, "x": x_thread, "source": url}, indent=2),
        encoding="utf-8",
    )

    if not dry_run:
        ledger.mark_many([url])
        ledger.flush()

    return PublishResult(
        url=url,
        title=post.title,
        linkedin=linkedin,
        x_thread=x_thread,
        already_distributed=False,
        dry_run=dry_run,
    )


def read_preview_html() -> str:
    path = preview_path()
    if not path.exists():
        return "<html><body><p>No preview yet. POST /publish first.</p></body></html>"
    return path.read_text(encoding="utf-8")


def _dry_run_variants(post: ScrapedPost) -> tuple[str, str]:
    linkedin = f"Dry run LinkedIn draft for: {post.title}\n\n{post.markdown[:200]}..."
    x_thread = f"1/ Dry run tweet about {post.title}\n\n2/ Key insight from the post.\n\n3/ Link in bio."
    return linkedin, x_thread


def _preview_html(title: str, url: str, linkedin: str, x_thread: str) -> str:
    from lib.ui import distribution_preview

    return distribution_preview(title=title, source_url=url, linkedin=linkedin, x_thread=x_thread)
