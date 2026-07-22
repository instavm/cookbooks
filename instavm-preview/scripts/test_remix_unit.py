#!/usr/bin/env python3
"""Unit test: remix catalog survives session expiry / pop."""

from __future__ import annotations

import asyncio
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.sessions import PreviewSession, SessionStore  # noqa: E402


async def main() -> int:
    store = SessionStore()
    sid = store.new_session_id()
    guest = "guest-a"
    other = "guest-b"
    session = PreviewSession(
        id=sid,
        guest_id=guest,
        client=SimpleNamespace(),
        sandbox=SimpleNamespace(),
        created_at=time.time(),
        expires_at=time.time() + 60,
        preview_url="https://example.test/preview",
        prompt="build a tiny hello page",
        template_id=None,
    )
    await store.put(session)

    live = await store.remix_payload(sid, guest)
    assert live and live["live"] is True and live["owned"] is True
    assert live["prompt"] == "build a tiny hello page"

    visitor = await store.remix_payload(sid, other)
    assert visitor and visitor["owned"] is False and visitor["live"] is True

    # Expire live session but keep remix catalog
    session.expires_at = time.time() - 1
    soft = await store.remix_payload(sid, other)
    assert soft and soft["live"] is False
    assert soft["prompt"] == "build a tiny hello page"
    assert soft["preview_url"] is None
    assert soft["owned"] is False

    await store.pop(sid)
    after_pop = await store.remix_payload(sid, guest)
    assert after_pop and after_pop["live"] is False
    assert after_pop["prompt"] == "build a tiny hello page"

    missing = await store.remix_payload("nope", guest)
    assert missing is None

    print("RESULT PASS remix unit")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
