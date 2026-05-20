from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential

FIRECRAWL_API = "https://api.firecrawl.dev/v1/scrape"


@dataclass
class ScrapedPost:
    url: str
    title: str
    markdown: str


def _mock_post(url: str) -> ScrapedPost:
    return ScrapedPost(
        url=url,
        title="Building AI agents on InstaVM",
        markdown=(
            "# Building AI agents on InstaVM\n\n"
            "We shipped cron VMs and persistent volumes this month. "
            "Founders can deploy production agents in under 30 minutes."
        ),
    )


def scrape_url(url: str, *, client: httpx.Client | None = None) -> ScrapedPost:
    if mock_enabled("FIRECRAWL_TEST_MODE") or mock_enabled("FIRECRAWL_MOCK"):
        return _mock_post(url)

    key = vault_credential("FIRECRAWL_API_KEY")
    http = client or httpx.Client(timeout=60.0)
    resp = http.post(
        FIRECRAWL_API,
        headers={"Authorization": f"Bearer {key}"},
        json={"url": url, "formats": ["markdown"]},
    )
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    return ScrapedPost(
        url=url,
        title=str(data.get("metadata", {}).get("title") or "Untitled"),
        markdown=str(data.get("markdown") or ""),
    )
