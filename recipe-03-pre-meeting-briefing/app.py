from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from lib.ui import landing_page
from lib.webhooks import enforce_cal_signature
from pydantic import BaseModel, Field, ValidationError

import agent
from lib.config import SAMPLE_ATTENDEE

app = FastAPI(title="Pre-Meeting Briefing")
_log = logging.getLogger(__name__)


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
    except Exception:
        _log.exception("run_briefing failed")
        raise HTTPException(status_code=502, detail="upstream error")
    return RunResponse(
        fetched=result.fetched,
        new=result.new,
        kept=result.kept,
        digest=result.digest,
        mail_sent=result.mail_sent,
        dry_run=result.dry_run,
    )


async def _verified_cal_event(request: Request) -> CalEvent:
    body_bytes = await request.body()
    enforce_cal_signature(body_bytes, request.headers.get("X-Cal-Signature-256"))
    try:
        payload = json.loads(body_bytes or b"{}")
        return CalEvent.model_validate(payload)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid payload") from exc


@app.post("/webhook/cal", response_model=CalWebhookResponse)
async def webhook_cal(request: Request, dry_run: bool = False) -> CalWebhookResponse:
    event = await _verified_cal_event(request)
    try:
        result = agent.build_briefing(event.model_dump(), dry_run=dry_run)
    except HTTPException:
        raise
    except Exception:
        _log.exception("build_briefing failed")
        raise HTTPException(status_code=502, detail="upstream error")
    return CalWebhookResponse(
        attendee_name=result.attendee_name,
        attendee_email=result.attendee_email,
        company=result.company,
        research_count=result.research_count,
        dry_run=result.dry_run,
        saved_path=result.saved_path,
    )


@app.post("/webhook/cal/markdown")
async def webhook_cal_markdown(request: Request, dry_run: bool = False) -> PlainTextResponse:
    event = await _verified_cal_event(request)
    try:
        result = agent.build_briefing(event.model_dump(), dry_run=dry_run)
    except HTTPException:
        raise
    except Exception:
        _log.exception("build_briefing failed")
        raise HTTPException(status_code=502, detail="upstream error")
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
