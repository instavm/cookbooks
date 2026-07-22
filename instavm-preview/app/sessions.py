"""In-memory preview sessions, guest quotas, and concurrency caps."""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from . import config


@dataclass
class PreviewSession:
    id: str
    guest_id: str
    client: Any
    sandbox: Any
    created_at: float
    expires_at: float
    preview_url: str | None = None
    iterates_used: int = 0
    prompt: str = ""
    template_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_requests: int = 0
    cleanup_task: asyncio.Task | None = field(default=None, repr=False)


@dataclass
class GuestQuota:
    guest_id: str
    day_key: str
    builds: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, PreviewSession] = {}
        # Survives sandbox TTL so /?remix= still recovers the prompt.
        self._remix: dict[str, dict[str, Any]] = {}
        self._guests: dict[str, GuestQuota] = {}
        self._lock = asyncio.Lock()
        self._active_builds = 0
        self._background: set[asyncio.Task] = set()
        self._remix_cap = 500

    @property
    def active_builds(self) -> int:
        return self._active_builds

    async def begin_build(self) -> None:
        async with self._lock:
            if self._active_builds >= config.MAX_CONCURRENT_BUILDS:
                raise RuntimeError(
                    f"Too many builds in progress (max {config.MAX_CONCURRENT_BUILDS}). Try again shortly."
                )
            self._active_builds += 1

    async def end_build(self) -> None:
        async with self._lock:
            self._active_builds = max(0, self._active_builds - 1)

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    async def check_guest_build_quota(self, guest_id: str) -> GuestQuota:
        async with self._lock:
            today = self._today()
            q = self._guests.get(guest_id)
            if q is None or q.day_key != today:
                q = GuestQuota(guest_id=guest_id, day_key=today, builds=0)
                self._guests[guest_id] = q
            if q.builds >= config.GUEST_BUILDS_PER_DAY:
                raise RuntimeError(
                    f"Daily guest limit reached ({config.GUEST_BUILDS_PER_DAY} builds). "
                    "Create a free InstaVM account to continue."
                )
            return q

    async def record_guest_build(self, guest_id: str) -> GuestQuota:
        async with self._lock:
            today = self._today()
            q = self._guests.get(guest_id)
            if q is None or q.day_key != today:
                q = GuestQuota(guest_id=guest_id, day_key=today, builds=0)
                self._guests[guest_id] = q
            q.builds += 1
            return q

    async def record_guest_tokens(
        self,
        guest_id: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
    ) -> GuestQuota:
        async with self._lock:
            today = self._today()
            q = self._guests.get(guest_id)
            if q is None or q.day_key != today:
                q = GuestQuota(guest_id=guest_id, day_key=today, builds=0)
                self._guests[guest_id] = q
            q.input_tokens += max(0, int(input_tokens))
            q.output_tokens += max(0, int(output_tokens))
            q.total_tokens += max(0, int(total_tokens))
            return q

    async def guest_status(self, guest_id: str) -> dict[str, Any]:
        async with self._lock:
            today = self._today()
            q = self._guests.get(guest_id)
            builds = q.builds if q and q.day_key == today else 0
            return {
                "guest_id": guest_id,
                "builds_used": builds,
                "builds_limit": config.GUEST_BUILDS_PER_DAY,
                "builds_remaining": max(0, config.GUEST_BUILDS_PER_DAY - builds),
                "iterates_per_session": config.GUEST_ITERATES_PER_SESSION,
                "tokens_used_today": q.total_tokens if q and q.day_key == today else 0,
                "input_tokens_today": q.input_tokens if q and q.day_key == today else 0,
                "output_tokens_today": q.output_tokens if q and q.day_key == today else 0,
            }

    async def put(self, session: PreviewSession) -> None:
        async with self._lock:
            self._sessions[session.id] = session
            self._remix[session.id] = {
                "prompt": session.prompt or "",
                "template_id": session.template_id,
                "preview_url": session.preview_url,
                "expires_at": session.expires_at,
                "guest_id": session.guest_id,
            }
            if len(self._remix) > self._remix_cap:
                # Drop oldest remix entries (dict insertion order).
                overflow = len(self._remix) - self._remix_cap
                for key in list(self._remix.keys())[:overflow]:
                    if key not in self._sessions:
                        self._remix.pop(key, None)

    async def get(self, session_id: str) -> PreviewSession | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if time.time() >= session.expires_at:
                return None
            return session

    async def remix_payload(
        self, session_id: str, guest_id: str
    ) -> dict[str, Any] | None:
        """Live session if available; otherwise prompt-only remix catalog entry."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and time.time() < session.expires_at:
                return {
                    "session_id": session.id,
                    "preview_url": session.preview_url,
                    "prompt": session.prompt,
                    "template_id": session.template_id,
                    "expires_at": session.expires_at,
                    "live": True,
                    "owned": session.guest_id == guest_id,
                    "iterates_used": session.iterates_used,
                    "iterates_remaining": max(
                        0,
                        config.GUEST_ITERATES_PER_SESSION - session.iterates_used,
                    ),
                    "usage": {
                        "input_tokens": session.input_tokens,
                        "output_tokens": session.output_tokens,
                        "total_tokens": session.total_tokens,
                        "requests": session.llm_requests,
                        "model": config.MODEL_NAME,
                    },
                }
            meta = self._remix.get(session_id)
            if not meta:
                return None
            return {
                "session_id": session_id,
                "preview_url": None,
                "prompt": meta.get("prompt") or "",
                "template_id": meta.get("template_id"),
                "expires_at": meta.get("expires_at"),
                "live": False,
                "owned": False,
                "iterates_used": 0,
                "iterates_remaining": 0,
                "usage": None,
            }

    async def pop(self, session_id: str) -> PreviewSession | None:
        async with self._lock:
            return self._sessions.pop(session_id, None)

    async def all_sessions(self) -> list[PreviewSession]:
        async with self._lock:
            return list(self._sessions.values())

    def track_task(self, task: asyncio.Task) -> None:
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    @staticmethod
    def new_session_id() -> str:
        return secrets.token_urlsafe(16)

    @staticmethod
    def new_guest_id() -> str:
        return secrets.token_urlsafe(12)


store = SessionStore()
