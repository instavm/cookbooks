from pathlib import Path

import httpx

from agent import resolve_accounts, run_monitor, save_accounts
from integrations.linkup import AccountNews, fetch_account_news
from lib.diff_store import FingerprintStore


def test_fetch_account_news_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": "Acme launched a new product line."})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    news = fetch_account_news("acme.com", client=client)
    assert news.domain == "acme.com"
    assert "product" in news.answer
    assert len(news.fingerprint) == 16


def test_fingerprint_diff(tmp_path: Path):
    store = FingerprintStore(tmp_path / "seen.json")
    assert store.is_new("acme.com", "abc")
    store.set("acme.com", "abc")
    store.flush()
    store2 = FingerprintStore(tmp_path / "seen.json")
    assert not store2.is_new("acme.com", "abc")
    assert store2.is_new("acme.com", "def")


def test_run_monitor_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    save_accounts(["acme.com", "globex.io"])

    calls = {"n": 0}

    def fake_fetch(domain, *, client=None):
        calls["n"] += 1
        return AccountNews(domain=domain, answer=f"News for {domain}", fingerprint=f"fp-{domain}")

    monkeypatch.setattr("agent.fetch_account_news", fake_fetch)
    result = run_monitor(dry_run=True)
    assert result.dry_run is True
    assert result.accounts_checked == 2
    assert result.new_signal == 2


def test_resolve_accounts_from_env(monkeypatch):
    monkeypatch.setenv("ABM_ACCOUNTS", "a.com,b.com")
    assert resolve_accounts() == ["a.com", "b.com"]
