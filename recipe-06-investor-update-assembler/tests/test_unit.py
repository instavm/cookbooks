from pathlib import Path

import httpx

from agent import load_kpi_history, run_assemble, save_kpi_snapshot
from integrations.github import GitHubMetrics, fetch_github_metrics
from integrations.stripe import StripeMetrics, fetch_stripe_metrics


def test_stripe_mock_metrics(monkeypatch):
    monkeypatch.setenv("STRIPE_TEST_MODE", "1")
    metrics = fetch_stripe_metrics()
    assert metrics.mrr_usd > 0
    assert metrics.month


def test_github_mock_without_token(monkeypatch):
    monkeypatch.setenv("GITHUB_MOCK", "1")
    metrics = fetch_github_metrics()
    assert metrics.commits_this_month >= 0


def test_github_parses_commits(monkeypatch):
    monkeypatch.setenv("GITHUB_MOCK", "0")
    monkeypatch.setenv("ALLOW_LOCAL_SECRETS", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPO", "org/repo")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[{"sha": "abc"}, {"sha": "def"}])
        return httpx.Response(200, json=[{"merged_at": "2026-05-01T00:00:00Z"}])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    metrics = fetch_github_metrics(client=client)
    assert metrics.commits_this_month == 2
    assert metrics.prs_merged_this_month == 1


def test_kpi_history_persisted(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    stripe = StripeMetrics(mrr_usd=1000.0, new_customers_this_month=1, churned_this_month=0, month="2026-05")
    github = GitHubMetrics(commits_this_month=5, prs_merged_this_month=2)
    save_kpi_snapshot(stripe, github)
    history = load_kpi_history()
    assert len(history) == 1
    assert history[0]["stripe"]["mrr_usd"] == 1000.0


def test_run_assemble_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STRIPE_TEST_MODE", "1")
    monkeypatch.setenv("GITHUB_MOCK", "1")
    result = run_assemble(dry_run=True)
    assert result.dry_run is True
    assert "MRR" in result.update
