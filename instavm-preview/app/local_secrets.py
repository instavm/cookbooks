"""Load secrets for local Preview runs (never required on deployed InstaVM)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("instavm_preview.secrets")

# User-requested canonical local key paths under Documents/projects.
PROJECTS_INSTAVM_KEY = Path("/Users/abhishekanand/Documents/projects/.instavm")
PROJECTS_OPENAI_KEY = Path("/Users/abhishekanand/Documents/projects/.openai")
CLI_CONFIG = Path.home() / ".instavm" / "config.json"
LOCAL_SECRETS_DIR = Path.home() / ".instavm" / "secrets"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _parse_dotenv_value(text: str, *names: str) -> str:
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        key = key.strip()
        if key not in names:
            continue
        val = val.strip().strip("'").strip('"')
        if val:
            return val
    return ""


def _openai_from_file(path: Path) -> str:
    """Accept a raw key file or a mini dotenv (OPENAI_API_KEY=...)."""
    text = _read_text(path)
    if not text:
        return ""
    if "=" in text.splitlines()[0]:
        return _parse_dotenv_value(text, "OPENAI_API_KEY", "OPENAI_KEY") or text
    return text


def load_instavm_api_key() -> str:
    """Resolve INSTAVM_API_KEY for local orchestrator → api.instavm.io calls."""
    env = (os.environ.get("INSTAVM_API_KEY") or "").strip()
    if env:
        return env

    file_key = _read_text(PROJECTS_INSTAVM_KEY)
    if file_key:
        logger.info("Loaded INSTAVM_API_KEY from %s", PROJECTS_INSTAVM_KEY)
        return file_key

    if CLI_CONFIG.is_file():
        try:
            data = json.loads(CLI_CONFIG.read_text(encoding="utf-8"))
            profiles = data.get("profiles") or {}
            active = data.get("active_profile") or "default"
            auth = (profiles.get(active) or profiles.get("default") or {}).get("auth") or {}
            key = (auth.get("api_key") or "").strip()
            if key:
                logger.info("Loaded INSTAVM_API_KEY from %s", CLI_CONFIG)
                return key
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    return ""


def load_openai_api_key() -> str:
    """Resolve OPENAI_API_KEY for the Agents SDK (runs in the orchestrator process)."""
    env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env:
        return env

    file_key = _openai_from_file(PROJECTS_OPENAI_KEY)
    if file_key:
        logger.info("Loaded OPENAI_API_KEY from %s", PROJECTS_OPENAI_KEY)
        return file_key

    for name in ("OPENAI_API_KEY", "openai"):
        path = LOCAL_SECRETS_DIR / name
        val = _read_text(path)
        if val:
            logger.info("Loaded OPENAI_API_KEY from %s", path)
            return val

    # Package-local .env (gitignored)
    pkg_env = Path(__file__).resolve().parent.parent / ".env"
    if pkg_env.is_file():
        val = _parse_dotenv_value(
            _read_text(pkg_env), "OPENAI_API_KEY", "OPENAI_KEY"
        )
        if val:
            logger.info("Loaded OPENAI_API_KEY from %s", pkg_env)
            return val

    return ""


def apply_local_secrets(*, force: bool = False) -> dict[str, bool]:
    """Populate os.environ for local runs. Safe no-op if keys already set.

    Set PREVIEW_LOCAL=1 (or call with force=True) to enable file-based loading.
    Deployed cookbooks leave PREVIEW_LOCAL unset and keep vault placeholders.
    """
    enabled = force or os.environ.get("PREVIEW_LOCAL", "").lower() in (
        "1",
        "true",
        "yes",
    )
    loaded = {"instavm": False, "openai": False}
    if not enabled:
        return loaded

    if not (os.environ.get("INSTAVM_API_KEY") or "").strip():
        key = load_instavm_api_key()
        if key:
            os.environ["INSTAVM_API_KEY"] = key
            loaded["instavm"] = True

    if not (os.environ.get("OPENAI_API_KEY") or "").strip():
        key = load_openai_api_key()
        if key:
            os.environ["OPENAI_API_KEY"] = key
            loaded["openai"] = True

    return loaded
