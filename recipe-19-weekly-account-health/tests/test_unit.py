from pathlib import Path

from agent import run_health_digest
from integrations.stripe import fetch_account_metrics
from lib.history import append_entry, load_history


def test_fetch_metrics_mock(monkeypatch):
    monkeypatch.setenv("STRIPE_MOCK", "1")
    metrics = fetch_account_metrics()
    assert metrics.mrr > 0
    assert metrics.active_subs > 0


def test_history_append(tmp_path: Path):
    path = tmp_path / "weekly_history.json"
    append_entry(path, {"mrr": 100.0, "week": "2026-01-01"})
    history = load_history(path)
    assert len(history) == 1


def test_run_health_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STRIPE_MOCK", "1")
    result = run_health_digest(dry_run=True)
    assert result.dry_run is True
    assert result.mrr > 0
