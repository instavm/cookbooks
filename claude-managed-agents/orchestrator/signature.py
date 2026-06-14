"""Anthropic webhook signature verification (fail-closed).

Anthropic signs webhook deliveries with the Standard Webhooks scheme using a
``whsec_``-prefixed signing key. The official path is the Anthropic SDK's
``client.beta.webhooks.unwrap()`` helper, which verifies the signature and
freshness in one step. We use it when available and fall back to a small,
dependency-free Standard Webhooks verifier so the cookbook stays testable
offline.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Mapping

_log = logging.getLogger(__name__)

# Standard Webhooks rejects payloads whose timestamp is too far from now.
_MAX_SKEW_SECONDS = 5 * 60


class WebhookError(Exception):
    """Raised when a webhook delivery cannot be trusted."""


def webhook_verify_enabled() -> bool:
    """Verification is ON by default; opt out only in local dev/CI."""
    return os.environ.get("WEBHOOK_VERIFY", "1").lower() not in {"0", "false", "no"}


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = {k.lower(): v for k, v in headers.items()}
    return lowered.get(name.lower())


def _verify_standard_webhooks(body: bytes, headers: Mapping[str, str], signing_key: str) -> None:
    webhook_id = _header(headers, "webhook-id")
    timestamp = _header(headers, "webhook-timestamp")
    signature = _header(headers, "webhook-signature") or _header(headers, "x-webhook-signature")
    if not (webhook_id and timestamp and signature):
        raise WebhookError("missing webhook signature headers")

    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise WebhookError("invalid webhook timestamp") from exc
    if abs(time.time() - ts) > _MAX_SKEW_SECONDS:
        raise WebhookError("webhook timestamp outside tolerance")

    secret = signing_key
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_") :]
    try:
        key_bytes = base64.b64decode(secret)
    except Exception:  # noqa: BLE001 - non-base64 secrets are used raw
        key_bytes = secret.encode()

    signed = b"%s.%s.%s" % (webhook_id.encode(), timestamp.encode(), body)
    expected = base64.b64encode(hmac.new(key_bytes, signed, hashlib.sha256).digest()).decode()

    # The header is a space-separated list of "version,signature" pairs.
    for part in signature.split():
        _, _, candidate = part.partition(",")
        if candidate and hmac.compare_digest(candidate, expected):
            return
    raise WebhookError("invalid webhook signature")


def _verify_with_sdk(body: bytes, headers: Mapping[str, str], signing_key: str) -> bool:
    """Best-effort verification via the Anthropic SDK. Returns True if it ran.

    Returns ``False`` (so the caller falls back to the built-in Standard Webhooks
    verifier) when the SDK or its optional ``anthropic[webhooks]`` extra is not
    available. Only a genuine signature mismatch raises :class:`WebhookError`.
    """
    try:
        import anthropic
    except Exception:  # noqa: BLE001 - SDK optional in tests
        return False

    def _unwrap(key_in_env: bool) -> None:
        if key_in_env:
            os.environ["ANTHROPIC_WEBHOOK_SIGNING_KEY"] = signing_key
            client = anthropic.Anthropic(api_key="not-used")
        else:
            client = anthropic.Anthropic(api_key="not-used", webhook_signing_key=signing_key)
        client.beta.webhooks.unwrap(body.decode("utf-8"), headers=dict(headers))

    try:
        _unwrap(key_in_env=False)
        return True
    except TypeError:
        # Older/newer SDKs read the key from ANTHROPIC_WEBHOOK_SIGNING_KEY.
        try:
            _unwrap(key_in_env=True)
            return True
        except Exception as exc:  # noqa: BLE001
            if _is_missing_webhooks_extra(exc):
                return False
            raise WebhookError(f"signature verification failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        if _is_missing_webhooks_extra(exc):
            return False
        raise WebhookError(f"signature verification failed: {exc}") from exc


def _is_missing_webhooks_extra(exc: Exception) -> bool:
    """True if the SDK couldn't verify because ``anthropic[webhooks]`` is absent."""
    msg = str(exc).lower()
    return "anthropic[webhooks]" in msg or "install" in msg and "webhook" in msg


def verify_and_parse(body: bytes, headers: Mapping[str, str], signing_key: str) -> dict[str, Any]:
    """Verify a webhook delivery and return the parsed JSON payload.

    Raises :class:`WebhookError` if the signature is missing/invalid (fail closed).
    Verification is skipped only when ``WEBHOOK_VERIFY`` is explicitly disabled or
    during ``DEPLOY_SMOKE`` runs.
    """
    from lib.secrets import VAULT_PLACEHOLDERS, deploy_smoke_mode

    def _parse() -> dict[str, Any]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise WebhookError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise WebhookError("webhook body must be a JSON object")
        return payload

    placeholder = VAULT_PLACEHOLDERS.get("ANTHROPIC_WEBHOOK_SIGNING_KEY", "")
    if not webhook_verify_enabled() or deploy_smoke_mode():
        return _parse()
    if not signing_key or signing_key == placeholder:
        _log.error("webhook signing key not bound; refusing delivery")
        raise WebhookError("webhook signing key not configured")

    if not _verify_with_sdk(body, headers, signing_key):
        _verify_standard_webhooks(body, headers, signing_key)
    return _parse()


def extract_session_event(payload: Mapping[str, Any]) -> tuple[str, str]:
    """Return ``(event_type, session_id)`` from a parsed webhook payload."""
    data = payload.get("data")
    if isinstance(data, Mapping):
        return str(data.get("type") or ""), str(data.get("id") or "")
    return str(payload.get("type") or ""), str(payload.get("id") or "")
