from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent
from lib.config import SAMPLE_ATTENDEE

app = FastAPI(title="Pre-Meeting Briefing")


class RunResponse(BaseModel):
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


class CalWebhookResponse(BaseModel):
    attendee_name: str
    attendee_email: str
    company: str
    research_count: int
    dry_run: bool
    saved_path: str | None = None


class CalEvent(BaseModel):
    attendees: list[dict[str, Any]] = Field(default_factory=list)
    startTime: str = ""
    title: str = "Meeting"
    organizer: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-03-pre-meeting-briefing",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_briefing(SAMPLE_ATTENDEE, dry_run=dry_run)
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


@app.post("/webhook/cal", response_model=CalWebhookResponse)
def webhook_cal(event: CalEvent, dry_run: bool = False) -> CalWebhookResponse:
    try:
        result = agent.build_briefing(event.model_dump(), dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CalWebhookResponse(
        attendee_name=result.attendee_name,
        attendee_email=result.attendee_email,
        company=result.company,
        research_count=result.research_count,
        dry_run=result.dry_run,
        saved_path=result.saved_path,
    )


@app.post("/webhook/cal/markdown")
def webhook_cal_markdown(event: CalEvent, dry_run: bool = False) -> PlainTextResponse:
    try:
        result = agent.build_briefing(event.model_dump(), dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PlainTextResponse(result.briefing, media_type="text/markdown")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Pre-Meeting Briefing",
            slug="recipe-03-pre-meeting-briefing",
            tagline="Cal.com webhook → Exa research → one-page attendee briefing.",
            endpoints=[
        ("POST", "/webhook/cal", "Meeting booked payload from Cal.com."),
        ("POST", "/run?dry_run=1", "Smoke briefing with sample attendee.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

