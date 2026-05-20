from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.config import LINEAR_TEAM
from lib.secrets import mock_enabled, vault_credential

LINEAR_GRAPHQL = "https://api.linear.app/graphql"


@dataclass
class LinearIssue:
    id: str
    title: str
    state: str
    assignee: str


def _mock_issues() -> list[LinearIssue]:
    return [
        LinearIssue(id="ENG-101", title="Ship standup digest", state="In Progress", assignee="alex"),
        LinearIssue(id="ENG-102", title="Wire Slack blocks", state="Todo", assignee="sam"),
    ]


def fetch_team_issues(*, client: httpx.Client | None = None) -> list[LinearIssue]:
    if mock_enabled("LINEAR_MOCK"):
        return _mock_issues()

    http = client or httpx.Client(timeout=20.0)
    key = vault_credential("LINEAR_API_KEY") or os.environ.get("LINEAR_API_KEY", "")
    query = """
    query($team: String!) {
      team(id: $team) {
        issues(first: 20, filter: { state: { type: { neq: \"completed\" } } }) {
          nodes { id title state { name } assignee { name } }
        }
      }
    }
    """
    resp = http.post(
        LINEAR_GRAPHQL,
        headers={"Authorization": key, "Content-Type": "application/json"},
        json={"query": query, "variables": {"team": LINEAR_TEAM}},
    )
    resp.raise_for_status()
    nodes = resp.json().get("data", {}).get("team", {}).get("issues", {}).get("nodes", [])
    issues: list[LinearIssue] = []
    for node in nodes:
        issues.append(
            LinearIssue(
                id=str(node.get("id", "")),
                title=str(node.get("title", "")),
                state=str((node.get("state") or {}).get("name", "")),
                assignee=str((node.get("assignee") or {}).get("name", "unassigned")),
            )
        )
    return issues
