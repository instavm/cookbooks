from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from lib.config import competitor_list

app = FastAPI(title="Competitor Launch Watcher")


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
        "slug": "recipe-02-competitor-launch-watcher",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "competitors": str(len(competitor_list())),
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_watch(dry_run=dry_run)
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
            title="Competitor Launch Watcher",
            slug="recipe-02-competitor-launch-watcher",
            tagline="Diff competitor launch pages and summarize what changed.",
            endpoints=[
        ("POST", "/run?dry_run=1", "Fetch competitor pages and diff titles.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

