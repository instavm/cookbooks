from __future__ import annotations

from dataclasses import dataclass

from exa_py import Exa

from lib.secrets import mock_enabled, vault_credential_strict


@dataclass
class VCResult:
    url: str
    title: str
    snippet: str


def search_vcs(
    thesis: str,
    *,
    limit: int = 20,
    exa: Exa | None = None,
) -> list[VCResult]:
    if mock_enabled("EXA_MOCK"):
        return [
            VCResult(
                url="https://example.vc/seed-ai",
                title="Example Seed Fund",
                snippet=f"Mock VC matching thesis: {thesis}",
            )
        ]
    client = exa or Exa(api_key=vault_credential_strict("EXA_API_KEY"))
    response = client.search_and_contents(
        f"venture capital investor {thesis} seed pre-seed portfolio",
        num_results=limit,
        type="neural",
        text={"max_characters": 800},
    )
    results: list[VCResult] = []
    for hit in response.results:
        text = getattr(hit, "text", "") or ""
        results.append(
            VCResult(
                url=getattr(hit, "url", "") or "",
                title=getattr(hit, "title", None) or "Untitled",
                snippet=text[:400],
            )
        )
    return [r for r in results if r.url]
