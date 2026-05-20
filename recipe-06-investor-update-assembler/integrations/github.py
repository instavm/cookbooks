from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

import httpx

from lib.config import GITHUB_REPO
from lib.secrets import mock_enabled, vault_credential


GITHUB_API = "https://api.github.com"


@dataclass
class GitHubMetrics:
    commits_this_month: int
    prs_merged_this_month: int

    def to_dict(self) -> dict:
        return asdict(self)


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


def fetch_github_metrics(*, client: httpx.Client | None = None) -> GitHubMetrics:
    if mock_enabled("GITHUB_MOCK"):
        return GitHubMetrics(commits_this_month=42, prs_merged_this_month=8)

    token = vault_credential("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO", GITHUB_REPO)
    since = _month_start_iso()

    http = client or httpx.Client(timeout=30.0)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    commits_resp = http.get(
        f"{GITHUB_API}/repos/{repo}/commits",
        headers=headers,
        params={"since": since, "per_page": 100},
    )
    commits_resp.raise_for_status()
    commits = commits_resp.json()
    commit_count = len(commits) if isinstance(commits, list) else 0

    pulls_resp = http.get(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers=headers,
        params={"state": "closed", "per_page": 100},
    )
    pulls_resp.raise_for_status()
    pulls = pulls_resp.json()
    merged = 0
    if isinstance(pulls, list):
        merged = sum(1 for p in pulls if (p.get("merged_at") or "") >= since)

    return GitHubMetrics(commits_this_month=commit_count, prs_merged_this_month=merged)
