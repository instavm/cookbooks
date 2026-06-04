from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import httpx


class CassetteMiss(Exception):
    pass


def _fingerprint(method: str, url: str, body: bytes) -> str:
    return f"{method.upper()} {url} {hashlib.sha256(body or b'').hexdigest()}"


class CassetteReplayClient:
    """Minimal offline cassette replay (compatible with InstaVM tape layout)."""

    def __init__(self, tape_id: str, *, cassette_root: str, strict: bool = True) -> None:
        self.tape_id = tape_id
        self.strict = strict
        self.path = Path(cassette_root) / tape_id / "llm_call.jsonl"
        self._queue: dict[str, list[dict[str, Any]]] = {}
        self.loaded = 0
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            self.loaded += 1
            entry = json.loads(line)
            payload = entry.get("payload") or entry
            req = payload.get("request") or {}
            method = str(req.get("method", "POST"))
            url = str(req.get("url", ""))
            body = b""
            if req.get("body_b64"):
                body = base64.b64decode(req["body_b64"])
            elif req.get("body_sha256"):
                body = b""
            key = _fingerprint(method, url, body)
            self._queue.setdefault(key, []).append(payload.get("response") or {})

    def lookup(self, method: str, url: str, body: bytes) -> dict[str, Any] | None:
        key = _fingerprint(method, url, body)
        items = self._queue.get(key) or []
        if not items:
            if self.strict:
                raise CassetteMiss(key)
            return None
        return items.pop(0)

    def as_httpx_transport(self) -> httpx.BaseTransport:
        client = self

        class _Transport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                recorded = client.lookup(request.method, str(request.url), request.content)
                if recorded is None:
                    return httpx.Response(502, json={"error": "cassette miss"})
                body = base64.b64decode(recorded.get("body_b64") or "")
                headers = {k: v for k, v in (recorded.get("headers") or [])}
                return httpx.Response(int(recorded.get("status", 200)), headers=headers, content=body)

        return _Transport()
