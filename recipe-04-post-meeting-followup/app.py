from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent
from lib.config import SAMPLE_TRANSCRIPT

app = FastAPI(title="Post-Meeting Follow-up")


class RunResponse(BaseModel):
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


class TranscriptPayload(BaseModel):
    title: str = "Meeting"
    attendee_email: str = ""
    attendee_name: str = ""
    transcript: str = ""


class FollowupResponse(BaseModel):
    subject: str
    body: str
    action_items: list[str] = Field(default_factory=list)
    saved_path: str | None = None
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-04-post-meeting-followup",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_followup(SAMPLE_TRANSCRIPT, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RunResponse(
        fetched=result.fetched,
        new=result.new,
        kept=result.kept,
        digest=result.digest,
        mail_sent=result.mail_sent,
        dry_run=result.dry_run,
    )


@app.post("/webhook/transcript", response_model=FollowupResponse)
def webhook_transcript(payload: TranscriptPayload, dry_run: bool = False) -> FollowupResponse:
    try:
        result = agent.process_transcript(payload.model_dump(), dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return FollowupResponse(
        subject=result.subject,
        body=result.body,
        action_items=result.action_items,
        saved_path=result.saved_path,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Post-Meeting Follow-up",
            slug="recipe-04-post-meeting-followup",
            tagline="Meeting transcript to structured follow-up email draft.",
            endpoints=[
        ("POST", "/webhook/transcript", "Paste or POST transcript JSON.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

