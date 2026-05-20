from pathlib import Path

from agent import read_preview_html, run_publish
from integrations.firecrawl import scrape_url
from lib.store import JsonStore


def test_firecrawl_mock(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_TEST_MODE", "1")
    post = scrape_url("https://example.substack.com/p/test")
    assert "InstaVM" in post.markdown
    assert post.title


def test_publish_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIRECRAWL_TEST_MODE", "1")
    url = "https://example.substack.com/p/test"
    result = run_publish(url, dry_run=True)
    assert result.dry_run is True
    assert result.linkedin
    assert "LinkedIn" in read_preview_html()


def test_ledger_skips_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIRECRAWL_TEST_MODE", "1")
    url = "https://example.substack.com/p/test"
    store = JsonStore(tmp_path / "distributed_ledger.json")
    store.mark_many([url])
    store.flush()
    result = run_publish(url, dry_run=False)
    assert result.already_distributed is True
