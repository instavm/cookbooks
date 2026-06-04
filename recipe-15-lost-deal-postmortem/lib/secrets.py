"""Credentials. InstaVM vault placeholders in production, local files for dev/tests only."""

from __future__ import annotations

import os
from pathlib import Path

# Names bound via `instavm vault setup .` / vault service templates.
VAULT_PLACEHOLDERS: dict[str, str] = {
    "OPENAI_API_KEY": "OPENAI_KEY",
    "ANTHROPIC_API_KEY": "ANTHROPIC_KEY",
    "EXA_API_KEY": "EXA_KEY",
    "FIRECRAWL_API_KEY": "FIRECRAWL_KEY",
    "STRIPE_KEY": "STRIPE_KEY",
    "STRIPE_RESTRICTED_KEY": "STRIPE_KEY",
    "GITHUB_TOKEN": "GITHUB_KEY",
    "LINEAR_API_KEY": "LINEAR_KEY",
    "LINKUP_API_KEY": "LINKUP_KEY",
    "NOTION_TOKEN": "NOTION_KEY",
    "NOTION_API_KEY": "NOTION_KEY",
    "CARTESIA_API_KEY": "CARTESIA_KEY",
    "MAILTRAP_API_TOKEN": "MAILTRAP_KEY",
    "SLACK_WEBHOOK_URL": "SLACK_WEBHOOK_URL",
    "SLACK_TOKEN": "SLACK_KEY",
    "SLACK_SIGNING_SECRET": "SLACK_SIGNING_SECRET",
    "GITHUB_WEBHOOK_SECRET": "GITHUB_WEBHOOK_SECRET",
    "CAL_WEBHOOK_SECRET": "CAL_WEBHOOK_SECRET",
    "INSTAVM_API_KEY": "INSTAVM_KEY",
}

_DEFAULT_SERVICES = Path.home() / ".instavm" / "secrets"
_DEFAULT_KNOWN: dict[str, Path] = {
    "OPENAI_API_KEY": _DEFAULT_SERVICES / "openai",
    "ANTHROPIC_API_KEY": _DEFAULT_SERVICES / "anthropic",
    "MAILTRAP_API_TOKEN": _DEFAULT_SERVICES / "mailtrap",
}


def _services_dir() -> Path:
    override = os.environ.get("INSTAVM_LOCAL_SECRETS_DIR", "").strip()
    return Path(override) if override else _DEFAULT_SERVICES


def allow_local_secrets() -> bool:
    return os.environ.get("ALLOW_LOCAL_SECRETS", "0").lower() in {"1", "true", "yes"}


def deploy_smoke_mode() -> bool:
    """True when running instavm deploy smoke tests with dummy vault placeholders."""
    return os.environ.get("DEPLOY_SMOKE", "").lower() in {"1", "true", "yes"}


def mock_enabled(flag: str) -> bool:
    if deploy_smoke_mode():
        return True
    return os.environ.get(flag, "").lower() in {"1", "true", "yes"}


def load_secret(name: str, default: str = "") -> str:
    """Read real credentials from local files. Dev and CI only, never required on InstaVM."""
    if not allow_local_secrets():
        return default
    services = _services_dir()
    path = services / name
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    known = _DEFAULT_KNOWN.get(name)
    if known and known.is_file():
        return known.read_text(encoding="utf-8").strip()
    return default


def vault_credential(name: str, *, placeholder: str | None = None) -> str:
    """Env override, else local dev file, else vault placeholder for egress injection.

    Local fallback reads from ~/.instavm/secrets/<NAME> (override with
    INSTAVM_LOCAL_SECRETS_DIR) and only when ALLOW_LOCAL_SECRETS=1.
    """
    ph = placeholder or VAULT_PLACEHOLDERS.get(name, name)
    env_val = (os.environ.get(name) or "").strip()
    if env_val:
        return env_val
    if allow_local_secrets():
        local = load_secret(name)
        if local:
            return local
    return ph


def vault_credential_strict(name: str, *, placeholder: str | None = None) -> str:
    """Like vault_credential but raises if only the placeholder is available.

    Use at upstream call sites where calling with a placeholder string would
    burn quota on a guaranteed-401. Skipped during DEPLOY_SMOKE.
    """
    value = vault_credential(name, placeholder=placeholder)
    if deploy_smoke_mode():
        return value
    ph = placeholder or VAULT_PLACEHOLDERS.get(name, name)
    if value == ph:
        raise RuntimeError(
            f"Credential {name!r} not bound: resolved to vault placeholder. "
            "Bind the secret via `instavm vault setup .` or set the env var."
        )
    return value


def secret_available(name: str) -> bool:
    if allow_local_secrets() and load_secret(name):
        return True
    env = (os.environ.get(name) or "").strip()
    ph = VAULT_PLACEHOLDERS.get(name, "")
    return bool(env and env != ph)
