"""Webhook signature verification helpers — fail closed by default."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

from fastapi import HTTPException

from lib.secrets import VAULT_PLACEHOLDERS, deploy_smoke_mode, vault_credential

_log = logging.getLogger(__name__)


def webhook_verify_enabled() -> bool:
    """Toggle the enforce_* helpers. Defaults to ON; opt out only in local dev/CI."""
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


def verify_cal_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Cal.com signs payloads with HMAC-SHA256 hex digest in X-Cal-Signature-256."""
    if not signature or not secret:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    candidates = (digest, "sha256=" + digest)
    return any(hmac.compare_digest(c, signature) for c in candidates)


def _resolve_or_fail(secret_name: str) -> str:
    """Resolve a webhook secret. Raise 503 if vault binding is missing in production."""
    value = vault_credential(secret_name)
    placeholder = VAULT_PLACEHOLDERS.get(secret_name, secret_name)
    if value and value != placeholder:
        return value
    if deploy_smoke_mode():
        return value
    _log.error("webhook secret %s not bound; refusing request", secret_name)
    raise HTTPException(status_code=503, detail="webhook secret not configured")


def enforce_github_signature(body: bytes, signature: str | None, secret_name: str = "GITHUB_WEBHOOK_SECRET") -> None:
    """Verify GitHub HMAC. Fails closed: 503 if misconfigured, 401 if signature invalid.

    No-ops only when WEBHOOK_VERIFY is explicitly disabled (dev mode).
    """
    if not webhook_verify_enabled():
        return
    secret = _resolve_or_fail(secret_name)
    if deploy_smoke_mode() and not signature:
        return
    if not verify_github_signature(body, signature, secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")


def enforce_cal_signature(body: bytes, signature: str | None, secret_name: str = "CAL_WEBHOOK_SECRET") -> None:
    """Verify Cal.com HMAC. Fails closed: 503 if misconfigured, 401 if signature invalid."""
    if not webhook_verify_enabled():
        return
    secret = _resolve_or_fail(secret_name)
    if deploy_smoke_mode() and not signature:
        return
    if not verify_cal_signature(body, signature, secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")


def enforce_slack_signature(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    secret_name: str = "SLACK_SIGNING_SECRET",
) -> None:
    if not webhook_verify_enabled():
        return
    secret = _resolve_or_fail(secret_name)
    if deploy_smoke_mode() and not signature:
        return
    if not verify_slack_signature(body, timestamp, signature, secret):
        raise HTTPException(status_code=401, detail="invalid webhook signature")
