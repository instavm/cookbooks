"""Exa company research — HTTP client with mock-friendly transport."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential

EXA_SEARCH_URL = "https://api.exa.ai/search"


@dataclass(frozen=True)
class ExaHit:
    title: str
    url: str
    snippet: str


def research_company(
    company: str,
    *,
    domain: str = "",
    num_results: int = 3,
    client: httpx.Client | None = None,
) -> list[ExaHit]:
    if mock_enabled("EXA_MOCK"):
        return [
            ExaHit(
                title=f"{company} recent news",
                url=f"https://{domain or company.lower()}.com/news",
                snippet=f"Mock Exa snippet for outbound research on {company}.",
            )
        ]
    query = f"{company} {domain} recent news 2026".strip()
    key = vault_credential("EXA_API_KEY")
    owns_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.post(
            EXA_SEARCH_URL,
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json={
                "query": query,
                "numResults": num_results,
                "useAutoprompt": True,
                "contents": {"text": {"maxCharacters": 400}},
            },
        )
        resp.raise_for_status()
        hits: list[ExaHit] = []
        for row in resp.json().get("results") or []:
            hits.append(
                ExaHit(
                    title=str(row.get("title") or ""),
                    url=str(row.get("url") or ""),
                    snippet=str((row.get("text") or "")[:400]),
                )
            )
        return hits
    finally:
        if owns_client:
            http.close()
