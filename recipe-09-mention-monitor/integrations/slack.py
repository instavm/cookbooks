from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential


@dataclass
class SlackResult:
    sent: bool
    dry_run: bool
    status_code: int | None = None


def post_alert(
    *,
    text: str,
    dry_run: bool = False,
    client: httpx.Client | None = None,
) -> SlackResult:
    if dry_run or mock_enabled("SLACK_MOCK") or os.environ.get("SLACK_DRY_RUN", "0") == "1":
        return SlackResult(sent=False, dry_run=True)

    webhook = vault_credential("SLACK_WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        return SlackResult(sent=False, dry_run=True)

    http = client or httpx.Client(timeout=15.0)
    resp = http.post(webhook, json={"text": text})
    resp.raise_for_status()
    return SlackResult(sent=True, dry_run=False, status_code=resp.status_code)
