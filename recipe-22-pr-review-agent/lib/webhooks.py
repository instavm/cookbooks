"""Optional webhook signature verification for inbound POST handlers."""

from __future__ import annotations

import hashlib
import hmac
import os


def webhook_verify_enabled() -> bool:
    return os.environ.get("WEBHOOK_VERIFY", "1").lower() not in {"0", "false", "no"}


def verify_github_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_slack_signature(body: bytes, timestamp: str | None, signature: str | None, secret: str) -> bool:
    if not timestamp or not signature or not secret:
        return False
    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
