from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from lib.ui import landing_page
from pydantic import BaseModel

import agent

app = FastAPI(title="Market Brief Voice")


class BriefResponse(BaseModel):
    stories: int
    new_stories: int
    script: str
    audio_bytes: int
    tts_stub: bool
    skipped: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-11-market-brief-voice",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/run", response_model=BriefResponse)
def run(dry_run: bool = False) -> BriefResponse:
    try:
        result = agent.run_brief(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return BriefResponse(
        stories=result.stories,
        new_stories=result.new_stories,
        script=result.script,
        audio_bytes=result.audio_bytes,
        tts_stub=result.tts_stub,
        skipped=result.skipped,
        dry_run=result.dry_run,
    )


@app.get("/audio/latest")
def audio_latest() -> Response:
    data = agent.read_latest_audio()
    if not data:
        raise HTTPException(status_code=404, detail="No audio generated yet")
    return Response(content=data, media_type="audio/mpeg")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Market Brief Voice",
            slug="recipe-11-market-brief-voice",
            tagline="Market news script with optional Cartesia TTS output.",
            endpoints=[
        ("POST", "/run?dry_run=1", "Generate script."),
        ("GET", "/audio/latest", "Latest MP3 brief.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

