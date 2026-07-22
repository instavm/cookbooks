"""InstaVM Preview — configuration."""

from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return int(raw)


MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")  # default plan
PREVIEW_PORT = 8080
PREVIEW_TTL_SECONDS = _int("VIBE_PREVIEW_TTL_SECONDS", 900)
SANDBOX_MEMORY_MB = _int("VIBE_SANDBOX_MEMORY_MB", 2048)
SANDBOX_TIMEOUT = max(PREVIEW_TTL_SECONDS, 600)
HEARTBEAT_INTERVAL_S = float(os.environ.get("VIBE_SSE_HEARTBEAT_S", "8"))

# Prod sandbox sessions run as uid=1000 (appuser). /workspace is not writable
# (and often missing), so use the home workspace the agent can mkdir.
WORKSPACE_ROOT = os.environ.get(
    "PREVIEW_WORKSPACE_ROOT", "/home/appuser/workspace"
).rstrip("/") or "/home/appuser/workspace"

# App data (sqlite/duckdb files). Prefer this over /tmp so iterate keeps state.
DATA_DIR = os.environ.get(
    "PREVIEW_DATA_DIR", f"{WORKSPACE_ROOT}/app/data"
).rstrip("/") or f"{WORKSPACE_ROOT}/app/data"

# When a volume is mounted (v2 / durable sandboxes), put DB files here instead.
VOLUME_DATA_DIR = os.environ.get(
    "PREVIEW_VOLUME_DATA_DIR", ""
).rstrip("/")

# Guest quotas (in-process; fine for single-orchestrator deploy).
GUEST_BUILDS_PER_DAY = _int("PREVIEW_GUEST_BUILDS_PER_DAY", 5)
GUEST_ITERATES_PER_SESSION = _int("PREVIEW_GUEST_ITERATES_PER_SESSION", 8)
MAX_CONCURRENT_BUILDS = _int("PREVIEW_MAX_CONCURRENT_BUILDS", 8)
MAX_PROMPT_CHARS = _int("PREVIEW_MAX_PROMPT_CHARS", 4000)
MAX_ATTACHMENTS = _int("PREVIEW_MAX_ATTACHMENTS", 3)
MAX_ATTACHMENT_BYTES = _int("PREVIEW_MAX_ATTACHMENT_BYTES", 4 * 1024 * 1024)
ALLOWED_ATTACHMENT_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)
DEFAULT_VISION_PROMPT = (
    "Build a polished web app that closely matches the attached screenshot(s). "
    "Match layout, typography, colors, spacing, and hierarchy as faithfully as "
    "possible. Prefer static HTML/CSS under the public folder."
)

DASH_URL = os.environ.get("INSTAVM_DASH_URL", "https://dash.instavm.io").rstrip("/")
SIGNUP_URL = os.environ.get(
    "INSTAVM_SIGNUP_URL", f"{DASH_URL}/auth/signup"
)
BILLING_URL = os.environ.get(
    "INSTAVM_BILLING_URL", f"{DASH_URL}/dashboard/usage"
)
PUBLIC_ORIGIN = os.environ.get("PREVIEW_PUBLIC_ORIGIN", "").rstrip("/")
POSTHOG_KEY = os.environ.get("NEXT_PUBLIC_POSTHOG_KEY", "")
POSTHOG_HOST = os.environ.get(
    "NEXT_PUBLIC_POSTHOG_HOST", "https://us.i.posthog.com"
)
PRODUCT_NAME = "InstaVM Preview"
