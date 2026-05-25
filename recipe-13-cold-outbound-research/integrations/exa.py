"""Exa company research via the official exa-py SDK."""

from __future__ import annotations

from dataclasses import dataclass

from exa_py import Exa

from lib.secrets import mock_enabled, vault_credential_strict


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
    exa: Exa | None = None,
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
    client = exa or Exa(api_key=vault_credential_strict("EXA_API_KEY"))
    response = client.search_and_contents(
        query,
        num_results=num_results,
        use_autoprompt=True,
        text={"max_characters": 400},
    )
    hits: list[ExaHit] = []
    for row in response.results:
        text = getattr(row, "text", "") or ""
        hits.append(
            ExaHit(
                title=getattr(row, "title", None) or "",
                url=getattr(row, "url", "") or "",
                snippet=text[:400],
            )
        )
    return hits
