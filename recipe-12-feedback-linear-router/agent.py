"""Feedback router — Slack webhook, LLM classify, Linear issue creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from integrations.linear import LinearIssue, create_issue
from lib.config import routed_path
from lib.llm import LLMClient
from lib.store import JsonStore

CLASSIFY_SYSTEM = """Classify customer feedback for routing.
Return JSON: {"category": "bug|feature|question|other", "priority": 1-4, "title": "short title", "route": true|false}
Route bugs and high-priority feature requests (route=true). Skip greetings and noise."""


@dataclass
class RouteResult:
    ref_id: str
    text: str
    category: str
    routed: bool
    issue: LinearIssue | None
    dry_run: bool
    skipped: bool


def handle_slack_event(
    body: dict[str, Any],
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> RouteResult | dict[str, str]:
    if body.get("type") == "url_verification":
        return {"challenge": str(body.get("challenge", ""))}

    event = body.get("event") or {}
    if event.get("type") != "message" or event.get("bot_id"):
        return RouteResult(ref_id="", text="", category="", routed=False, issue=None, dry_run=dry_run, skipped=True)

    text = str(event.get("text") or "").strip()
    channel = str(event.get("channel") or "unknown")
    ts = str(event.get("ts") or "")
    ref_id = f"{channel}:{ts}"

    if len(text) < 20:
        return RouteResult(ref_id=ref_id, text=text, category="other", routed=False, issue=None, dry_run=dry_run, skipped=True)

    store = JsonStore(routed_path())
    if store.seen(ref_id):
        return RouteResult(ref_id=ref_id, text=text, category="", routed=False, issue=None, dry_run=dry_run, skipped=True)

    if dry_run:
        classification = {"category": "bug", "priority": 2, "title": text[:80], "route": True}
    else:
        client = llm or LLMClient(client=http)
        classification = client.complete_json(CLASSIFY_SYSTEM, text[:1000])

    category = str(classification.get("category") or "other")
    should_route = bool(classification.get("route"))
    title = str(classification.get("title") or text[:80])
    priority = int(classification.get("priority") or 3)

    issue = None
    routed = False
    if should_route and not dry_run:
        issue = create_issue(title=f"[SLACK] {title}", description=text, priority=priority, client=http)
        routed = True
        store.mark_many([ref_id])
        store.flush()
    elif should_route and dry_run:
        routed = True
        issue = LinearIssue(id="dry-run", title=f"[SLACK] {title}", url="")

    return RouteResult(
        ref_id=ref_id,
        text=text,
        category=category,
        routed=routed,
        issue=issue,
        dry_run=dry_run,
        skipped=False,
    )
