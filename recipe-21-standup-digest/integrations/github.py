from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from lib.config import GITHUB_REPO
from lib.secrets import mock_enabled, vault_credential

GITHUB_COMMITS = "https://api.github.com/repos/{repo}/commits"


@dataclass
class Commit:
    sha: str
    message: str
    author: str


def _mock_commits() -> list[Commit]:
    return [
        Commit(sha="abc1234", message="feat: standup digest agent", author="dev@instavm.io"),
        Commit(sha="def5678", message="fix: slack block formatting", author="dev@instavm.io"),
    ]


def fetch_recent_commits(*, since_days: int = 1, client: httpx.Client | None = None) -> list[Commit]:
    if mock_enabled("GITHUB_MOCK"):
        return _mock_commits()

    since = (date.today() - timedelta(days=since_days)).isoformat()
    http = client or httpx.Client(timeout=20.0)
    token = vault_credential("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    resp = http.get(
        GITHUB_COMMITS.format(repo=GITHUB_REPO),
        params={"since": f"{since}T00:00:00Z", "per_page": 20},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    resp.raise_for_status()
    commits: list[Commit] = []
    for row in resp.json():
        commit = row.get("commit", {})
        commits.append(
            Commit(
                sha=str(row.get("sha", ""))[:7],
                message=str(commit.get("message", "")).split("\n")[0],
                author=str(commit.get("author", {}).get("email", "unknown")),
            )
        )
    return commits
