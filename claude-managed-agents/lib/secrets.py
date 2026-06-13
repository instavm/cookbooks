"""Credentials. InstaVM vault placeholders in production, env/local files for dev only.

The whole point of this cookbook is that the *worker* microVM never receives a
naked provider credential — the InstaVM egress proxy substitutes the real value
from the bound org vault at TLS write time. Code therefore ships placeholder
strings (e.g. ``ANTHROPIC_KEY``) and lets the platform inject the real secret on
outbound HTTPS.

The orchestrator itself needs a small number of *control-plane* secrets in
process (the webhook signing key, used for local HMAC verification, and the
InstaVM API key, used to spawn worker microVMs). Those are resolved here too.
"""

from __future__ import annotations

import os
from pathlib import Path

# Logical credential name -> egress placeholder string. The org vault maps a
# service host (api.anthropic.com) to the real credential behind these names.
VAULT_PLACEHOLDERS: dict[str, str] = {
    "ANTHROPIC_API_KEY": "ANTHROPIC_KEY",
    "ANTHROPIC_ENVIRONMENT_KEY": "ANTHROPIC_ENV_KEY",
    "ANTHROPIC_WEBHOOK_SIGNING_KEY": "ANTHROPIC_WHSEC",
    "INSTAVM_API_KEY": "INSTAVM_KEY",
}

_DEFAULT_SERVICES = Path.home() / ".instavm" / "secrets"


def _services_dir() -> Path:
    override = os.environ.get("INSTAVM_LOCAL_SECRETS_DIR", "").strip()
    return Path(override) if override else _DEFAULT_SERVICES


def allow_local_secrets() -> bool:
    return os.environ.get("ALLOW_LOCAL_SECRETS", "0").lower() in {"1", "true", "yes"}


def deploy_smoke_mode() -> bool:
    """True when running `instavm deploy` smoke tests with dummy vault placeholders."""
    return os.environ.get("DEPLOY_SMOKE", "").lower() in {"1", "true", "yes"}


def load_secret(name: str, default: str = "") -> str:
    """Read a real credential from a local file. Dev and CI only."""
    if not allow_local_secrets():
        return default
    path = _services_dir() / name
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return default


def vault_credential(name: str, *, placeholder: str | None = None) -> str:
    """Env override, else local dev file, else the egress placeholder string."""
    ph = placeholder or VAULT_PLACEHOLDERS.get(name, name)
    env_val = (os.environ.get(name) or "").strip()
    if env_val:
        return env_val
    if allow_local_secrets():
        local = load_secret(name)
        if local:
            return local
    return ph


def secret_available(name: str) -> bool:
    """True when ``name`` resolves to a real value (not just a placeholder)."""
    if allow_local_secrets() and load_secret(name):
        return True
    env = (os.environ.get(name) or "").strip()
    ph = VAULT_PLACEHOLDERS.get(name, "")
    return bool(env and env != ph)
