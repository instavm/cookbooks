from agent import run_standup
from integrations.github import fetch_recent_commits
from integrations.linear import fetch_team_issues


def test_github_mock(monkeypatch):
    monkeypatch.setenv("GITHUB_MOCK", "1")
    commits = fetch_recent_commits()
    assert len(commits) >= 1


def test_linear_mock(monkeypatch):
    monkeypatch.setenv("LINEAR_MOCK", "1")
    issues = fetch_team_issues()
    assert len(issues) >= 1


def test_run_standup_dry_run(monkeypatch):
    monkeypatch.setenv("GITHUB_MOCK", "1")
    monkeypatch.setenv("LINEAR_MOCK", "1")
    result = run_standup(dry_run=True)
    assert result.dry_run is True
    assert result.commits >= 1
