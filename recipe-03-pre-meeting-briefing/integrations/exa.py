from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential

EXA_SEARCH_URL = "https://api.exa.ai/search"


@dataclass
class ResearchHit:
    url: str
    title: str
    snippet: str


def research_attendee(
    name: str,
    company: str,
    email: str,
    *,
    client: httpx.Client | None = None,
) -> list[ResearchHit]:
    if mock_enabled("EXA_MOCK"):
        return [
            ResearchHit(
                url=f"https://{company.lower().replace(' ', '')}.com/about",
                title=f"{name} — {company}",
                snippet=f"Mock research context for {name} at {company}.",
            )
        ]
    http = client or httpx.Client(timeout=30.0)
    key = vault_credential("EXA_API_KEY")
    domain = email.split("@")[1] if "@" in email else ""
    queries = [
        f"{name} {company} investor founder",
        f"{company} funding round 2025 2026",
        f"site:{domain}" if domain else f"{company} news",
    ]
    hits: list[ResearchHit] = []
    for query in queries:
        resp = http.post(
            EXA_SEARCH_URL,
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json={
                "query": query,
                "numResults": 5,
                "type": "neural",
                "contents": {"text": {"maxCharacters": 600}},
            },
        )
        resp.raise_for_status()
        for item in resp.json().get("results", []):
            text = str(item.get("text") or "")
            hits.append(
                ResearchHit(
                    url=str(item.get("url") or ""),
                    title=str(item.get("title") or "Untitled"),
                    snippet=text[:300],
                )
            )
    seen: set[str] = set()
    unique: list[ResearchHit] = []
    for hit in hits:
        if hit.url and hit.url not in seen:
            seen.add(hit.url)
            unique.append(hit)
    return unique[:12]
