"""Background dispatch: turn a verified webhook into a ready worker microVM.

The webhook handler returns 200 immediately and schedules a dispatch task. The
dispatcher debounces briefly so a burst of near-simultaneous webhooks collapses
into a single spawn per session, then ensures a worker microVM exists for the
session.
"""

from __future__ import annotations

import asyncio
import logging

from orchestrator.config import dispatcher_debounce_ms
from orchestrator.worker_pool import WorkerInfo, WorkerPool

_log = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, pool: WorkerPool) -> None:
        self._pool = pool
        self._scheduled: set[str] = set()

    async def dispatch(self, session_id: str) -> WorkerInfo:
        """Ensure a worker exists for ``session_id`` (used directly in tests)."""
        return await self._pool.ensure_worker(session_id)

    def schedule(self, session_id: str) -> None:
        """Fire-and-forget background dispatch for a session."""
        if session_id in self._scheduled:
            return
        self._scheduled.add(session_id)
        asyncio.create_task(self._run(session_id))

    async def _run(self, session_id: str) -> None:
        try:
            debounce = dispatcher_debounce_ms()
            if debounce > 0:
                await asyncio.sleep(debounce / 1000)
            info = await self._pool.ensure_worker(session_id)
            if info.status == "failed":
                _log.error("dispatch for session %s failed: %s", session_id, info.error)
        except Exception:  # noqa: BLE001
            _log.exception("background dispatch for session %s crashed", session_id)
        finally:
            self._scheduled.discard(session_id)
