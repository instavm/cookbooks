from pathlib import Path

import httpx

from agent import run_watch
from integrations.competitors import PageSnapshot, extract_titles, fetch_page
from lib.store import TitleCache


def test_extract_titles():
    html = "<html><title>Launch 1</title><h1>New Feature</h1></html>"
    titles = extract_titles(html)
    assert "Launch 1" in titles
    assert "New Feature" in titles


def test_fetch_page_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><title>Changelog</title></html>")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    snap = fetch_page("https://example.com/blog", "Example", client=client)
    assert snap.titles == ["Changelog"]


def test_title_cache(tmp_path: Path):
    cache = TitleCache(tmp_path / "titles.json")
    cache.set("https://a.com", ["Old"])
    cache.flush()
    cache2 = TitleCache(tmp_path / "titles.json")
    assert cache2.get("https://a.com") == ["Old"]


def test_run_watch_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_fetch(competitors, *, client=None):
        return [PageSnapshot(url="https://a.com", name="A", titles=["New Launch"])]

    monkeypatch.setattr("agent.fetch_competitors", fake_fetch)
    result = run_watch(dry_run=True)
    assert result.dry_run is True
    assert result.fetched == 1
