from pathlib import Path

from agent import run_watch
from integrations.exa import search_patents
from integrations.firecrawl import search_competitors
from lib.store import JsonStore


def test_exa_mock(monkeypatch):
    monkeypatch.setenv("EXA_MOCK", "1")
    hits = search_patents("agent sandbox")
    assert len(hits) >= 1


def test_firecrawl_mock(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_MOCK", "1")
    hits = search_competitors("agent sandbox")
    assert len(hits) >= 1


def test_store_dedup(tmp_path: Path):
    store = JsonStore(tmp_path / "seen.json")
    assert not store.seen("p1")
    store.mark_many(["p1"])
    store.flush()
    assert JsonStore(tmp_path / "seen.json").seen("p1")


def test_run_watch_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EXA_MOCK", "1")
    monkeypatch.setenv("FIRECRAWL_MOCK", "1")
    result = run_watch(dry_run=True)
    assert result.dry_run is True
    assert result.new >= 1
