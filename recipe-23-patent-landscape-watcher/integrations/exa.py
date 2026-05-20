from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.config import PATENT_QUERY
from lib.secrets import mock_enabled, vault_credential

EXA_SEARCH = "https://api.exa.ai/search"


@dataclass
class PatentHit:
    id: str
    title: str
    url: str
    snippet: str
    source: str = "exa"


def _mock_hits() -> list[PatentHit]:
    return [
        PatentHit(
            id="exa-1",
            title="Systems for ephemeral agent sandboxes",
            url="https://patents.example.com/US1234567",
            snippet="A method for provisioning isolated compute for AI agents...",
        ),
        PatentHit(
            id="exa-2",
            title="Orchestrated VM lifecycle for LLM tools",
            url="https://patents.example.com/US7654321",
            snippet="Scheduling and egress control for tool-using models...",
        ),
    ]


def search_patents(query: str, *, limit: int = 10, client: httpx.Client | None = None) -> list[PatentHit]:
    if mock_enabled("EXA_MOCK"):
        return _mock_hits()[:limit]

    http = client or httpx.Client(timeout=30.0)
    key = vault_credential("EXA_API_KEY")
    resp = http.post(
        EXA_SEARCH,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json={"query": query or PATENT_QUERY, "numResults": limit, "type": "auto"},
    )
    resp.raise_for_status()
    hits: list[PatentHit] = []
    for row in resp.json().get("results", []):
        hits.append(
            PatentHit(
                id=str(row.get("id") or row.get("url", "")),
                title=str(row.get("title") or "Untitled"),
                url=str(row.get("url") or ""),
                snippet=str(row.get("text") or row.get("snippet") or "")[:300],
            )
        )
    return hits
