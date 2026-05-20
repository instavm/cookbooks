from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.config import PATENT_QUERY
from lib.secrets import mock_enabled, vault_credential

FIRECRAWL_SEARCH = "https://api.firecrawl.dev/v1/search"


@dataclass
class CompetitorHit:
    id: str
    title: str
    url: str
    snippet: str
    source: str = "firecrawl"


def _mock_hits() -> list[CompetitorHit]:
    return [
        CompetitorHit(
            id="fc-1",
            title="Competitor launches sandbox API",
            url="https://news.example.com/sandbox-api",
            snippet="New cloud sandbox targets AI agent developers...",
        ),
    ]


def search_competitors(query: str, *, limit: int = 10, client: httpx.Client | None = None) -> list[CompetitorHit]:
    if mock_enabled("FIRECRAWL_MOCK"):
        return _mock_hits()[:limit]

    http = client or httpx.Client(timeout=30.0)
    key = vault_credential("FIRECRAWL_API_KEY") or os.environ.get("FIRECRAWL_API_KEY", "")
    resp = http.post(
        FIRECRAWL_SEARCH,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": query or PATENT_QUERY, "limit": limit},
    )
    resp.raise_for_status()
    hits: list[CompetitorHit] = []
    for row in resp.json().get("data", []):
        hits.append(
            CompetitorHit(
                id=str(row.get("url", "")),
                title=str(row.get("title") or "Untitled"),
                url=str(row.get("url") or ""),
                snippet=str(row.get("description") or row.get("markdown") or "")[:300],
            )
        )
    return hits
