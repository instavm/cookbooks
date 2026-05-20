from __future__ import annotations

from dataclasses import dataclass

from exa_py import Exa

from lib.secrets import mock_enabled, vault_credential_strict


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
    exa: Exa | None = None,
) -> list[ResearchHit]:
    if mock_enabled("EXA_MOCK"):
        return [
            ResearchHit(
                url=f"https://{company.lower().replace(' ', '')}.com/about",
                title=f"{name} — {company}",
                snippet=f"Mock research context for {name} at {company}.",
            )
        ]
    client = exa or Exa(api_key=vault_credential_strict("EXA_API_KEY"))
    domain = email.split("@")[1] if "@" in email else ""
    queries = [
        f"{name} {company} investor founder",
        f"{company} funding round 2025 2026",
        f"site:{domain}" if domain else f"{company} news",
    ]
    hits: list[ResearchHit] = []
    for query in queries:
        response = client.search_and_contents(
            query,
            num_results=5,
            type="neural",
            text={"max_characters": 600},
        )
        for item in response.results:
            text = getattr(item, "text", "") or ""
            hits.append(
                ResearchHit(
                    url=getattr(item, "url", "") or "",
                    title=getattr(item, "title", None) or "Untitled",
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
