from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent

app = FastAPI(title="Voice Roadmap Notion")


class TranscriptPayload(BaseModel):
    transcript: str = Field(..., min_length=1)
    source: str = "cartesia"


class TranscriptResponse(BaseModel):
    items: list[dict]
    notion_appended: int
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-20-voice-roadmap-notion",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/webhook/transcript", response_model=TranscriptResponse)
def webhook_transcript(payload: TranscriptPayload, dry_run: bool = False) -> TranscriptResponse:
    try:
        result = agent.process_transcript(payload.transcript, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TranscriptResponse(
        items=result.items,
        notion_appended=result.notion_appended,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Voice Roadmap Notion",
            slug="recipe-20-voice-roadmap-notion",
            tagline="Voice transcript extracts roadmap items for Notion.",
            endpoints=[
        ("POST", "/webhook/transcript?dry_run=1", "Cartesia-style transcript webhook.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

