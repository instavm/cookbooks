from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

import httpx

from integrations.hn import Mention

REDDIT_SEARCH_RSS = "https://www.reddit.com/search.rss"


def _entry_text(entry: ET.Element, tag: str) -> str:
    el = entry.find(f"atom:{tag}", {"atom": "http://www.w3.org/2005/Atom"})
    return (el.text or "").strip() if el is not None else ""


def search_mentions(brand: str, *, limit: int = 10, client: httpx.Client | None = None) -> list[Mention]:
    http = client or httpx.Client(timeout=20.0, headers={"User-Agent": "mention-monitor/1.0"})
    resp = http.get(REDDIT_SEARCH_RSS, params={"q": brand, "sort": "new"})
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    mentions: list[Mention] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        title = _entry_text(entry, "title")
        link_el = entry.find("atom:link", ns)
        url = link_el.get("href", "") if link_el is not None else ""
        summary = _entry_text(entry, "summary") or title
        mid = hashlib.sha1((url + title).encode()).hexdigest()[:16]
        mentions.append(
            Mention(
                id=f"reddit-{mid}",
                title=title,
                url=url,
                source="reddit",
                text=summary,
            )
        )
    return mentions
