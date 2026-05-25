from __future__ import annotations

from dataclasses import dataclass

from exa_py import Exa

from lib.config import PATENT_QUERY
from lib.secrets import mock_enabled, vault_credential_strict


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


def search_patents(query: str, *, limit: int = 10, exa: Exa | None = None) -> list[PatentHit]:
    if mock_enabled("EXA_MOCK"):
        return _mock_hits()[:limit]

    client = exa or Exa(api_key=vault_credential_strict("EXA_API_KEY"))
    response = client.search_and_contents(
        query or PATENT_QUERY,
        num_results=limit,
        type="auto",
    )
    hits: list[PatentHit] = []
    for row in response.results:
        url = getattr(row, "url", "") or ""
        text = getattr(row, "text", "") or ""
        hits.append(
            PatentHit(
                id=str(getattr(row, "id", None) or url),
                title=getattr(row, "title", None) or "Untitled",
                url=url,
                snippet=text[:300],
            )
        )
    return hits
