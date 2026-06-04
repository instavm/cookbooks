from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled
_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)
_HEADING_RE = re.compile(r"<h[12][^>]*>([^<]+)</h[12]>", re.I)


@dataclass
class PageSnapshot:
    url: str
    name: str
    titles: list[str]


def extract_titles(html: str) -> list[str]:
    found = _TITLE_RE.findall(html) + _HEADING_RE.findall(html)
    seen: set[str] = set()
    titles: list[str] = []
    for raw in found:
        title = raw.strip()
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return titles[:10]


def fetch_page(url: str, name: str, *, client: httpx.Client | None = None) -> PageSnapshot:
    http = client or httpx.Client(timeout=20.0, follow_redirects=True)
    resp = http.get(url)
    resp.raise_for_status()
    return PageSnapshot(url=url, name=name, titles=extract_titles(resp.text))


def fetch_competitors(
    competitors: list[dict[str, str]],
    *,
    client: httpx.Client | None = None,
) -> list[PageSnapshot]:
    if mock_enabled("COMPETITOR_MOCK"):
        return [
            PageSnapshot(
                url=c["url"],
                name=c["name"],
                titles=[f"{c['name']} launch preview", f"{c['name']} changelog"],
            )
            for c in competitors
        ]
    return [fetch_page(c["url"], c["name"], client=client) for c in competitors]
