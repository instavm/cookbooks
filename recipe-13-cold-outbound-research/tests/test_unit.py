from pathlib import Path

import httpx

from agent import research_and_email
from integrations.exa import ExaHit, research_company
from lib.store import JsonStore


def test_research_company_parses(monkeypatch):
    monkeypatch.setenv("EXA_MOCK", "0")
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Acme raises Series B", "url": "https://news.com/a", "text": "Funding round"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    hits = research_company("Acme", domain="acme.com", client=client)
    assert len(hits) == 1
    assert hits[0].title == "Acme raises Series B"


def test_emailed_dedup(tmp_path: Path):
    store = JsonStore(tmp_path / "emailed.json")
    assert not store.seen("a@b.com")
    store.mark_many(["a@b.com"])
    store.flush()
    assert JsonStore(tmp_path / "emailed.json").seen("a@b.com")


def test_research_and_email_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_research(company, *, domain="", num_results=3, client=None):
        return [ExaHit(title="News", url="https://x.com", snippet="snippet")]

    monkeypatch.setattr("agent.research_company", fake_research)
    result = research_and_email(
        name="Pat",
        email="pat@acme.com",
        company="Acme",
        domain="acme.com",
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.research_hits == 1
    assert "Dry run" in result.body
