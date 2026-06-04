from __future__ import annotations

from dataclasses import dataclass

import httpx

HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"


@dataclass
class Mention:
    id: str
    title: str
    url: str
    source: str
    text: str


def search_mentions(brand: str, *, limit: int = 10, client: httpx.Client | None = None) -> list[Mention]:
    http = client or httpx.Client(timeout=20.0)
    resp = http.get(
        HN_ALGOLIA,
        params={"query": brand, "tags": "story,comment", "hitsPerPage": limit},
    )
    resp.raise_for_status()
    mentions: list[Mention] = []
    for hit in resp.json().get("hits", []):
        oid = str(hit.get("objectID", ""))
        if not oid:
            continue
        mentions.append(
            Mention(
                id=f"hn-{oid}",
                title=str(hit.get("title") or hit.get("comment_text", "")[:80] or "HN mention"),
                url=str(hit.get("url") or f"https://news.ycombinator.com/item?id={oid}"),
                source="hackernews",
                text=str(hit.get("comment_text") or hit.get("title") or ""),
            )
        )
    return mentions
