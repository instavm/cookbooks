"""SEO blog pipeline — topic to LLM draft with HTML preview."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from lib.config import draft_path
from lib.draft_store import DraftStore
from lib.llm import LLMClient

BLOG_SYSTEM = """You are an SEO content writer.
Return JSON only:
{
  "title": "H1 title with primary keyword",
  "meta_description": "150-160 chars",
  "slug": "url-slug",
  "keywords": ["primary", "secondary"],
  "outline": ["H2 sections"],
  "body_markdown": "full article in markdown, 400-600 words"
}"""


@dataclass
class BlogResult:
    topic: str
    draft: dict[str, Any]
    dry_run: bool


def generate_blog(
    topic: str,
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> BlogResult:
    if dry_run:
        draft = {
            "title": f"Dry run: {topic}",
            "meta_description": "Preview meta description for dry run.",
            "slug": "dry-run-preview",
            "keywords": [topic],
            "outline": ["Introduction", "Key points", "Conclusion"],
            "body_markdown": f"# {topic}\n\nDry run — LLM skipped.",
        }
        DraftStore(draft_path()).save(draft)
        return BlogResult(topic=topic, draft=draft, dry_run=True)

    client = llm or LLMClient(client=http)
    draft = client.complete_json(BLOG_SYSTEM, f"Topic: {topic}")
    draft.setdefault("title", topic)
    DraftStore(draft_path()).save(draft)
    return BlogResult(topic=topic, draft=draft, dry_run=False)


def load_preview() -> dict[str, Any] | None:
    return DraftStore(draft_path()).load()


def render_preview_html(draft: dict[str, Any]) -> str:
    from lib.ui import editorial_preview, markdown_to_html

    title = str(draft.get("title") or "Preview")
    body = str(draft.get("body_markdown") or "")
    meta = str(draft.get("meta_description") or "")
    return editorial_preview(
        title=title,
        meta=meta,
        body_html=markdown_to_html(body),
        eyebrow="SEO draft preview",
    )
