from __future__ import annotations

import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent

app = FastAPI(title="Lost Deal Post-Mortem")


class TranscriptRequest(BaseModel):
    transcript: str = Field(..., min_length=10)
    deal_name: str = ""


class PostmortemResponse(BaseModel):
    postmortem: dict
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-15-lost-deal-postmortem",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/transcript", response_model=PostmortemResponse)
def transcript_json(body: TranscriptRequest, dry_run: bool = False) -> PostmortemResponse:
    return _analyze(body.transcript, body.deal_name, dry_run=dry_run)


@app.post("/transcript/upload", response_model=PostmortemResponse)
async def transcript_upload(
    file: UploadFile = File(...),
    deal_name: str = Form(""),
    dry_run: bool = False,
) -> PostmortemResponse:
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")
    return _analyze(text, deal_name, dry_run=dry_run)


def _analyze(text: str, deal_name: str, *, dry_run: bool) -> PostmortemResponse:
    if len(text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Transcript too short")
    try:
        result = agent.analyze_transcript(text, deal_name=deal_name, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PostmortemResponse(postmortem=result.postmortem, dry_run=result.dry_run)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Lost Deal Post-Mortem",
            slug="recipe-15-lost-deal-postmortem",
            tagline="Closed-lost transcript to structured post-mortem.",
            endpoints=[
        ("POST", "/transcript?dry_run=1", "Analyze transcript JSON.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

