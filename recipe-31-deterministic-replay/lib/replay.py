from __future__ import annotations

import json
from pathlib import Path

import httpx

from lib.cassette import CassetteReplayClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TAPE_ID = "recipe31"
CHAT_URL = "https://api.openai.com/v1/chat/completions"
REPLAY_PROMPT = "Say REPLAY_OK"


def _ensure_tape_layout() -> Path:
    tape_dir = FIXTURES / TAPE_ID
    tape_dir.mkdir(parents=True, exist_ok=True)
    dest = tape_dir / "llm_call.jsonl"
    src = FIXTURES / "cassette.jsonl"
    if src.is_file() and (not dest.is_file() or dest.read_text() != src.read_text()):
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return FIXTURES


def make_replay_client(*, strict: bool = True) -> CassetteReplayClient:
    root = _ensure_tape_layout()
    return CassetteReplayClient(TAPE_ID, cassette_root=str(root), strict=strict)


def replay_chat_completion(client: CassetteReplayClient | None = None) -> str:
    cassette = client or make_replay_client()
    body = json.dumps(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": REPLAY_PROMPT}],
        }
    ).encode()
    transport = cassette.as_httpx_transport()
    with httpx.Client(transport=transport) as http:
        resp = http.post(CHAT_URL, content=body, headers={"content-type": "application/json"})
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    return str(message.get("content") or "")
