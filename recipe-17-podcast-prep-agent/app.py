from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent

app = FastAPI(title="Podcast Prep Agent")


class TranscriptRequest(BaseModel):
    transcript: str = Field(..., min_length=20)
    episode_title: str = ""
    with_tts: bool = False


class PrepResponse(BaseModel):
    show_notes: dict
    tts_stub: bool
    tts_bytes: int
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-17-podcast-prep-agent",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/transcript", response_model=PrepResponse)
def transcript(body: TranscriptRequest, dry_run: bool = False) -> PrepResponse:
    try:
        result = agent.prepare_episode(
            body.transcript,
            episode_title=body.episode_title,
            with_tts=body.with_tts,
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PrepResponse(
        show_notes=result.show_notes,
        tts_stub=result.tts_stub,
        tts_bytes=result.tts_bytes,
        dry_run=result.dry_run,
    )


@app.get("/notes")
def notes() -> JSONResponse:
    data = agent.load_notes()
    if not data:
        raise HTTPException(status_code=404, detail="No show notes yet")
    return JSONResponse(data)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Podcast Prep Agent",
            slug="recipe-17-podcast-prep-agent",
            tagline="Episode transcript to host show notes.",
            endpoints=[
        ("POST", "/transcript?dry_run=1", "Generate show notes.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

