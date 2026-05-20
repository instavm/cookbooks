from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.config import SLACK_CHANNEL
from lib.secrets import mock_enabled, vault_credential

SLACK_POST = "https://slack.com/api/chat.postMessage"


@dataclass
class SlackResult:
    sent: bool
    dry_run: bool
    channel: str


def post_standup(*, text: str, dry_run: bool = False, client: httpx.Client | None = None) -> SlackResult:
    if dry_run or mock_enabled("SLACK_MOCK") or os.environ.get("SLACK_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        return SlackResult(sent=False, dry_run=True, channel=SLACK_CHANNEL)

    token = vault_credential("SLACK_TOKEN") or os.environ.get("SLACK_TOKEN", "")
    http = client or httpx.Client(timeout=20.0)
    resp = http.post(
        SLACK_POST,
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": SLACK_CHANNEL, "text": text, "mrkdwn": True},
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("error", "slack_post_failed"))
    return SlackResult(sent=True, dry_run=False, channel=SLACK_CHANNEL)
