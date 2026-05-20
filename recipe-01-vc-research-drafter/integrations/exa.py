from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential

EXA_SEARCH_URL = "https://api.exa.ai/search"


@dataclass
class VCResult:
    url: str
    title: str
    snippet: str


def search_vcs(
    thesis: str,
    *,
    limit: int = 20,
    client: httpx.Client | None = None,
) -> list[VCResult]:
    if mock_enabled("EXA_MOCK"):
        return [
            VCResult(
                url="https://example.vc/seed-ai",
                title="Example Seed Fund",
                snippet=f"Mock VC matching thesis: {thesis}",
            )
        ]
    http = client or httpx.Client(timeout=30.0)
    key = vault_credential("EXA_API_KEY")
    resp = http.post(
        EXA_SEARCH_URL,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json={
            "query": f"venture capital investor {thesis} seed pre-seed portfolio",
            "numResults": limit,
            "type": "neural",
            "contents": {"text": {"maxCharacters": 800}},
        },
    )
    resp.raise_for_status()
    results: list[VCResult] = []
    for hit in resp.json().get("results", []):
        text = str(hit.get("text") or "")
        results.append(
            VCResult(
                url=str(hit.get("url") or ""),
                title=str(hit.get("title") or "Untitled"),
                snippet=text[:400],
            )
        )
    return [r for r in results if r.url]
