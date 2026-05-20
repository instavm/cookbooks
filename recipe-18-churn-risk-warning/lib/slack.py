from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential


@dataclass
class SlackResult:
    sent: bool
    dry_run: bool


def post_slack_message(text: str, *, client: httpx.Client | None = None) -> SlackResult:
    url = vault_credential("SLACK_WEBHOOK_URL") or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url or os.environ.get("SLACK_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        return SlackResult(sent=False, dry_run=True)

    owns_client = client is None
    http = client or httpx.Client(timeout=15.0)
    try:
        resp = http.post(url, json={"text": text})
        resp.raise_for_status()
        return SlackResult(sent=True, dry_run=False)
    finally:
        if owns_client:
            http.close()
