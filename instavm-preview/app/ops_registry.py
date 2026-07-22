"""Short-lived PTY proxy tokens — keep InstaVM API keys off the browser."""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any

_TTL_SECONDS = 6 * 60 * 60
_lock = threading.Lock()
_entries: dict[str, dict[str, Any]] = {}


def register(
    *,
    guest_id: str,
    session_id: str | None,
    vm_id: str | None,
    pty_id: str,
    upstream_ws: str,
) -> str:
    token = secrets.token_urlsafe(24)
    with _lock:
        _purge_locked()
        _entries[token] = {
            "guest_id": guest_id,
            "session_id": session_id,
            "vm_id": vm_id,
            "pty_id": pty_id,
            "upstream_ws": upstream_ws,
            "expires": time.time() + _TTL_SECONDS,
        }
    return token


def get(token: str, guest_id: str | None = None) -> dict[str, Any] | None:
    with _lock:
        _purge_locked()
        entry = _entries.get(token)
        if not entry:
            return None
        if guest_id and entry.get("guest_id") != guest_id:
            return None
        return dict(entry)


def _purge_locked() -> None:
    now = time.time()
    dead = [k for k, v in _entries.items() if v.get("expires", 0) < now]
    for k in dead:
        _entries.pop(k, None)
