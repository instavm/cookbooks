from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import agent
from lib.config import DIGEST_TO, HN_QUERY
from lib.ui import landing_page

app = FastAPI(title="HN Signal Scanner")


class RunResponse(BaseModel):
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-08-hn-signal-scanner",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "query": HN_QUERY,
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_scan(dry_run=dry_run)
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


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="HN Signal Scanner",
            slug="recipe-08-hn-signal-scanner",
            tagline="HN Algolia digest with LLM signal filter and Mailtrap delivery.",
            endpoints=[
                ("GET", "/health", "Liveness and config."),
                ("POST", "/run?dry_run=1", "Preview digest without email."),
            ],
            pills=["cron-style", "volume dedup"],
        )
    )
