"""GitHub PR webhook → LLM code review markdown."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from lib.llm import LLMClient

REVIEW_SYSTEM = """You are a senior engineer reviewing a pull request.
Return JSON: {
  "summary": "2-3 sentence overview",
  "risks": ["risk", ...],
  "suggestions": ["suggestion", ...],
  "verdict": "approve|request_changes|comment"
}
Be specific and actionable. Max 5 risks and 5 suggestions."""


@dataclass
class ReviewResult:
    pr_number: int
    title: str
    review_markdown: str
    verdict: str
    dry_run: bool


def review_pr(payload: dict[str, Any], *, dry_run: bool = False, llm: LLMClient | None = None, http: httpx.Client | None = None) -> ReviewResult:
    pr = payload.get("pull_request") or {}
    number = int(pr.get("number") or payload.get("number") or 0)
    title = str(pr.get("title") or "Untitled PR")
    context = (
        f"Repo: {(payload.get('repository') or {}).get('full_name', '')}\n"
        f"PR #{number}: {title}\n"
        f"Author: {(pr.get('user') or {}).get('login', 'unknown')}\n"
        f"Body: {pr.get('body', '')}\n"
        f"Stats: +{pr.get('additions', 0)}/-{pr.get('deletions', 0)} across {pr.get('changed_files', 0)} files\n"
        f"Branch: {(pr.get('head') or {}).get('ref', '')} → {(pr.get('base') or {}).get('ref', '')}"
    )

    if dry_run:
        markdown = f"## InstaVM PR Review (dry run)\n\n**{title}** — LLM skipped.\n\n{context[:500]}"
        return ReviewResult(pr_number=number, title=title, review_markdown=markdown, verdict="comment", dry_run=True)

    client = llm or LLMClient(client=http)
    parsed: dict[str, Any] = client.complete_json(REVIEW_SYSTEM, context)
    markdown = _to_markdown(title, parsed)
    return ReviewResult(
        pr_number=number,
        title=title,
        review_markdown=markdown,
        verdict=str(parsed.get("verdict") or "comment"),
        dry_run=False,
    )


def _to_markdown(title: str, parsed: dict[str, Any]) -> str:
    lines = [f"## InstaVM PR Review\n", f"**{title}**\n", str(parsed.get("summary") or ""), ""]
    risks = parsed.get("risks") or []
    if risks:
        lines.append("### Risks")
        lines.extend(f"- {r}" for r in risks)
        lines.append("")
    suggestions = parsed.get("suggestions") or []
    if suggestions:
        lines.append("### Suggestions")
        lines.extend(f"- {s}" for s in suggestions)
        lines.append("")
    lines.append(f"**Verdict:** `{parsed.get('verdict', 'comment')}`")
    return "\n".join(lines)
