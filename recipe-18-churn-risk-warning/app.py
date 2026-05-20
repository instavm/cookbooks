from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent

app = FastAPI(title="Churn Risk Warning")


class ScanResponse(BaseModel):
    accounts_scored: int
    high_risk: int
    assessment: dict
    slack_sent: bool
    mail_sent: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-18-churn-risk-warning",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/scan", response_model=ScanResponse)
def scan(dry_run: bool = False) -> ScanResponse:
    try:
        result = agent.scan_churn_risk(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ScanResponse(
        accounts_scored=result.accounts_scored,
        high_risk=result.high_risk,
        assessment=result.assessment,
        slack_sent=result.slack_sent,
        mail_sent=result.mail_sent,
        dry_run=result.dry_run,
    )


@app.get("/fixtures")
def fixtures() -> JSONResponse:
    return JSONResponse({"accounts": agent.load_fixtures()})


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Churn Risk Warning",
            slug="recipe-18-churn-risk-warning",
            tagline="Stripe billing + Intercom sentiment to churn risk alerts.",
            endpoints=[
        ("POST", "/scan?dry_run=1", "Score accounts."),
        ("GET", "/fixtures", "Bundled sample data.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

