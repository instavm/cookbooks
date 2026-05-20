from __future__ import annotations

import os
from dataclasses import dataclass
import httpx

from lib.config import LINEAR_TEAM_ID
from lib.secrets import mock_enabled, vault_credential

LINEAR_API = "https://api.linear.app/graphql"


@dataclass
class LinearIssue:
    id: str
    title: str
    url: str


def create_issue(
    *,
    title: str,
    description: str,
    priority: int = 2,
    client: httpx.Client | None = None,
) -> LinearIssue:
    if mock_enabled("LINEAR_TEST_MODE") or mock_enabled("LINEAR_MOCK"):
        return LinearIssue(id="mock-issue-1", title=title, url="https://linear.app/mock/issue-1")

    key = vault_credential("LINEAR_API_KEY")
    http = client or httpx.Client(timeout=30.0)
    mutation = """
    mutation IssueCreate($input: IssueCreateInput!) {
      issueCreate(input: $input) { success issue { id title url } }
    }
    """
    resp = http.post(
        LINEAR_API,
        headers={"Authorization": key, "Content-Type": "application/json"},
        json={
            "query": mutation,
            "variables": {
                "input": {
                    "teamId": LINEAR_TEAM_ID,
                    "title": title,
                    "description": description,
                    "priority": priority,
                }
            },
        },
    )
    resp.raise_for_status()
    issue = resp.json().get("data", {}).get("issueCreate", {}).get("issue") or {}
    return LinearIssue(
        id=str(issue.get("id") or "unknown"),
        title=str(issue.get("title") or title),
        url=str(issue.get("url") or ""),
    )
