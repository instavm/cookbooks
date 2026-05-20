"""Cartesia TTS stub — optional audio intro for show notes."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from lib.secrets import mock_enabled, vault_credential

CARTESIA_URL = "https://api.cartesia.ai/tts/bytes"


@dataclass(frozen=True)
class TTSResult:
    audio_bytes: bytes
    content_type: str
    stub: bool


def synthesize_intro(script: str, *, client: httpx.Client | None = None) -> TTSResult:
    """Call Cartesia when configured; otherwise return a stub payload."""
    if mock_enabled("CARTESIA_MOCK"):
        payload = f"[cartesia-stub] {script[:200]}".encode()
        return TTSResult(audio_bytes=payload, content_type="text/plain", stub=True)

    key = vault_credential("CARTESIA_API_KEY")
    if not key or key == "CARTESIA_KEY":
        payload = f"[cartesia-stub] {script[:200]}".encode()
        return TTSResult(audio_bytes=payload, content_type="text/plain", stub=True)

    owns_client = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        resp = http.post(
            CARTESIA_URL,
            headers={"Authorization": f"Bearer {key}", "Cartesia-Version": "2024-06-10"},
            json={
                "model_id": os.environ.get("CARTESIA_MODEL", "sonic-english"),
                "transcript": script[:500],
                "voice": {"mode": "id", "id": os.environ.get("CARTESIA_VOICE_ID", "default")},
                "output_format": {"container": "mp3", "encoding": "mp3", "sample_rate": 44100},
            },
        )
        resp.raise_for_status()
        return TTSResult(audio_bytes=resp.content, content_type="audio/mpeg", stub=False)
    finally:
        if owns_client:
            http.close()
