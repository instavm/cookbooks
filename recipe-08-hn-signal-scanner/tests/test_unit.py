from pathlib import Path

import httpx

from agent import run_scan
from integrations.hn import Story, fetch_stories
from lib.store import JsonStore


def test_fetch_stories_parses(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"hits": [{"objectID": "99", "title": "AI agents", "url": "https://x.com", "points": 42}]},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    stories = fetch_stories("ai", client=client)
    assert len(stories) == 1
    assert stories[0].id == "99"


def test_store_dedup(tmp_path: Path):
    store = JsonStore(tmp_path / "seen.json")
    assert not store.seen("a")
    store.mark_many(["a"])
    store.flush()
    store2 = JsonStore(tmp_path / "seen.json")
    assert store2.seen("a")


def test_run_scan_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_fetch(query, *, limit=30, client=None):
        return [Story(id="1", title="T", url="https://e.com", points=1)]

    monkeypatch.setattr("agent.fetch_stories", fake_fetch)
    result = run_scan(dry_run=True)
    assert result.dry_run is True
    assert result.new == 1
