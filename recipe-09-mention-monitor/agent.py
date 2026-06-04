"""Mention monitor — poll HN + Reddit, LLM score, Slack webhook alerts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from integrations import hn as hn_integration
from integrations import reddit as reddit_integration
from integrations.hn import Mention
from integrations.slack import post_alert
from lib.config import BRAND_NAME, MAX_MENTIONS, SCORE_THRESHOLD, seen_path
from lib.llm import LLMClient
from lib.store import JsonStore

SCORE_SYSTEM = """Rate brand mentions for relevance and urgency.
Return JSON: {"score": int 1-10, "summary": "one line", "sentiment": "positive|negative|neutral"}"""


@dataclass
class PollResult:
    polled: int
    new: int
    alerted: int
    dry_run: bool
    mentions: list[dict[str, Any]]


def run_poll(
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> PollResult:
    store = JsonStore(seen_path())
    brand = BRAND_NAME

    hn_mentions = hn_integration.search_mentions(brand, limit=MAX_MENTIONS, client=http)
    reddit_mentions = reddit_integration.search_mentions(brand, limit=MAX_MENTIONS, client=http)
    all_mentions = hn_mentions + reddit_mentions
    new_mentions = [m for m in all_mentions if not store.seen(m.id)]

    alerted = 0
    output: list[dict[str, Any]] = []

    for mention in new_mentions:
        if dry_run:
            rating = {"score": 8, "summary": mention.title[:100], "sentiment": "neutral"}
        else:
            client = llm or LLMClient(client=http)
            rating = client.complete_json(SCORE_SYSTEM, f"Brand: {brand}\n\n{mention.text[:800]}")

        score = int(rating.get("score") or 0)
        item = {
            "id": mention.id,
            "source": mention.source,
            "title": mention.title,
            "url": mention.url,
            "score": score,
            "summary": str(rating.get("summary") or ""),
            "sentiment": str(rating.get("sentiment") or "neutral"),
        }
        output.append(item)

        if score >= SCORE_THRESHOLD:
            emoji = {"positive": ":tada:", "negative": ":warning:", "neutral": ":speech_balloon:"}.get(
                item["sentiment"], ":speech_balloon:"
            )
            slack_text = (
                f"{emoji} *New {brand} mention* (score {score}/10)\n"
                f">{item['summary']}\n"
                f"Source: {mention.url}"
            )
            slack = post_alert(text=slack_text, dry_run=dry_run, client=http)
            if slack.sent or slack.dry_run:
                alerted += 1

    if not dry_run:
        store.mark_many(m.id for m in new_mentions)
        store.flush()

    return PollResult(
        polled=len(all_mentions),
        new=len(new_mentions),
        alerted=alerted,
        dry_run=dry_run,
        mentions=output,
    )
