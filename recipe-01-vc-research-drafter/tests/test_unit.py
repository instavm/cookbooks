from pathlib import Path

import httpx

from agent import run_draft
from integrations.exa import VCResult, search_vcs
from lib.store import JsonStore


def test_search_vcs_parses(monkeypatch):
    monkeypatch.setenv("EXA_MOCK", "0")
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.com/vc",
                        "title": "Acme Ventures",
                        "text": "Seed stage AI investor",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    vcs = search_vcs("AI infra", client=client)
    assert len(vcs) == 1
    assert vcs[0].url == "https://example.com/vc"


def test_store_dedup(tmp_path: Path):
    store = JsonStore(tmp_path / "seen.json")
    assert not store.seen("a")
    store.mark_many(["a"])
    store.flush()
    store2 = JsonStore(tmp_path / "seen.json")
    assert store2.seen("a")


def test_run_draft_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_search(thesis, *, limit=20, client=None):
        return [VCResult(url="https://vc.com", title="VC Fund", snippet="AI seed")]

    monkeypatch.setattr("agent.search_vcs", fake_search)
    result = run_draft(dry_run=True)
    assert result.dry_run is True
    assert result.new == 1
