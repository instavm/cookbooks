from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent
from lib.config import SAMPLE_EMAIL_SIGNAL

app = FastAPI(title="Investor CRM Updater")


class RunResponse(BaseModel):
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


class EmailSignal(BaseModel):
    from_name: str = ""
    from_email: str = ""
    subject: str = ""
    body_preview: str = ""


class CrmResponse(BaseModel):
    email: str
    record: dict[str, Any]
    created: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-05-investor-crm-updater",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_crm_update(SAMPLE_EMAIL_SIGNAL, dry_run=dry_run)
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


@app.post("/webhook/email-signal", response_model=CrmResponse)
def webhook_email_signal(signal: EmailSignal, dry_run: bool = False) -> CrmResponse:
    try:
        result = agent.process_email_signal(signal.model_dump(), dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CrmResponse(
        email=result.email,
        record=result.record,
        created=result.created,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Investor CRM Updater",
            slug="recipe-05-investor-crm-updater",
            tagline="Email signals upserted into a lightweight investor CRM JSON store.",
            endpoints=[
        ("POST", "/webhook/email-signal", "Inbound email signal JSON.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

