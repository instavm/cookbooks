from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential

LINKUP_API = "https://api.linkup.so/v1/search"


@dataclass
class NewsStory:
    id: str
    name: str
    url: str
    content: str


def _mock_stories() -> list[NewsStory]:
    return [
        NewsStory(
            id="mock-1",
            name="Markets steady as tech earnings beat",
            url="https://example.com/markets",
            content="Equities held gains as mega-cap tech reported stronger cloud revenue.",
        ),
        NewsStory(
            id="mock-2",
            name="Bond yields dip on soft inflation",
            url="https://example.com/bonds",
            content="Treasury yields fell after CPI came in below expectations.",
        ),
    ]


def fetch_news(*, client: httpx.Client | None = None) -> list[NewsStory]:
    if mock_enabled("LINKUP_TEST_MODE") or mock_enabled("LINKUP_MOCK"):
        return _mock_stories()

    key = vault_credential("LINKUP_API_KEY")
    http = client or httpx.Client(timeout=30.0)
    resp = http.post(
        LINKUP_API,
        headers={"Authorization": f"Bearer {key}"},
        json={"q": "market brief equities bonds macro", "depth": "standard", "outputType": "searchResults"},
    )
    resp.raise_for_status()
    stories: list[NewsStory] = []
    for item in resp.json().get("results", [])[:12]:
        url = str(item.get("url") or "")
        sid = hashlib.sha1(url.encode()).hexdigest()[:12] if url else "unknown"
        stories.append(
            NewsStory(
                id=sid,
                name=str(item.get("name") or "Untitled"),
                url=url,
                content=str(item.get("content") or ""),
            )
        )
    return stories
