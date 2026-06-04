"""Daily standup — GitHub commits + Linear issues → LLM digest → Slack."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from integrations.github import fetch_recent_commits
from integrations.linear import fetch_team_issues
from integrations.slack import post_standup
from lib.llm import LLMClient

STANDUP_SYSTEM = """You write a concise engineering standup digest for Slack.
Return JSON: {
  "yesterday": ["bullet", ...],
  "today": ["bullet", ...],
  "blockers": ["bullet", ...]
}
Use the commits and Linear issues provided. Max 4 bullets per section."""


@dataclass
class RunResult:
    commits: int
    issues: int
    digest: str
    slack_sent: bool
    dry_run: bool


def run_standup(*, dry_run: bool = False, llm: LLMClient | None = None, http: httpx.Client | None = None) -> RunResult:
    commits = fetch_recent_commits(client=http)
    issues = fetch_team_issues(client=http)

    commit_lines = [f"{c.sha} {c.message} ({c.author})" for c in commits]
    issue_lines = [f"{i.id} {i.title} [{i.state}] @{i.assignee}" for i in issues]
    context = f"Date: {date.today()}\nCommits:\n" + "\n".join(commit_lines) + "\n\nIssues:\n" + "\n".join(issue_lines)

    if dry_run:
        digest = f"*Standup Digest — {date.today()}*\n\nDry run — LLM and Slack skipped.\n\n{context[:800]}"
        return RunResult(commits=len(commits), issues=len(issues), digest=digest, slack_sent=False, dry_run=True)

    client = llm or LLMClient(client=http)
    parsed: dict[str, Any] = client.complete_json(STANDUP_SYSTEM, context)
    digest = _format_digest(parsed)
    slack = post_standup(text=digest, dry_run=False, client=http)
    return RunResult(commits=len(commits), issues=len(issues), digest=digest, slack_sent=slack.sent, dry_run=False)


def _format_digest(parsed: dict[str, Any]) -> str:
    sections = [
        ("*Yesterday*", parsed.get("yesterday") or []),
        ("*Today*", parsed.get("today") or []),
        ("*Blockers*", parsed.get("blockers") or []),
    ]
    lines = [f"*Standup Digest — {date.today()}*", ""]
    for title, bullets in sections:
        lines.append(title)
        for bullet in bullets:
            lines.append(f"• {bullet}")
        lines.append("")
    return "\n".join(lines).strip()
