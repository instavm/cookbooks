from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from lib.config import SLACK_CHANNEL

app = FastAPI(title="Weekly Account Health")


class RunResponse(BaseModel):
    mrr: float
    delta_mrr: float
    churn_count: int
    digest: str
    slack_sent: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-19-weekly-account-health",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "slack_channel": SLACK_CHANNEL,
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_health_digest(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RunResponse(
        mrr=result.mrr,
        delta_mrr=result.delta_mrr,
        churn_count=result.churn_count,
        digest=result.digest,
        slack_sent=result.slack_sent,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Weekly Account Health",
            slug="recipe-19-weekly-account-health",
            tagline="Weekly Stripe health digest posted to Slack.",
            endpoints=[
        ("POST", "/run?dry_run=1", "Preview weekly digest.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

