from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.config import CARTESIA_ENABLED
from lib.secrets import mock_enabled, vault_credential

CARTESIA_API = "https://api.cartesia.ai/tts/bytes"
PLACEHOLDER_MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00market-brief-placeholder"


@dataclass
class TTSResult:
    audio: bytes
    stub: bool


def synthesize(script: str, *, client: httpx.Client | None = None) -> TTSResult:
    if mock_enabled("CARTESIA_MOCK") or not CARTESIA_ENABLED:
        return TTSResult(audio=PLACEHOLDER_MP3 + script[:32].encode("utf-8"), stub=True)

    key = vault_credential("CARTESIA_API_KEY")
    http = client or httpx.Client(timeout=120.0)
    resp = http.post(
        CARTESIA_API,
        headers={"Authorization": f"Bearer {key}", "Cartesia-Version": "2024-06-10"},
        json={
            "model_id": "sonic-2",
            "transcript": script,
            "voice": {"mode": "id", "id": "694f9389-aac1-45b6-b726-9d9369183238"},
            "output_format": {"container": "mp3", "encoding": "mp3", "sample_rate": 44100},
        },
    )
    if resp.status_code >= 400:
        return TTSResult(audio=PLACEHOLDER_MP3, stub=True)
    return TTSResult(audio=resp.content, stub=False)
