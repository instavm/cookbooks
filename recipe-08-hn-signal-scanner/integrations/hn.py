from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"


@dataclass
class Story:
    id: str
    title: str
    url: str
    points: int


def fetch_stories(query: str, *, limit: int = 30, client: httpx.Client | None = None) -> list[Story]:
    http = client or httpx.Client(timeout=20.0)
    resp = http.get(HN_ALGOLIA, params={"query": query, "tags": "story", "hitsPerPage": limit})
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    stories: list[Story] = []
    for hit in hits:
        stories.append(
            Story(
                id=str(hit.get("objectID", "")),
                title=str(hit.get("title") or "Untitled"),
                url=str(hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"),
                points=int(hit.get("points") or 0),
            )
        )
    return [s for s in stories if s.id]
