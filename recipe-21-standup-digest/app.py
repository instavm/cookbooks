from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from lib.config import SLACK_CHANNEL

app = FastAPI(title="Standup Digest")


class RunResponse(BaseModel):
    commits: int
    issues: int
    digest: str
    slack_sent: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-21-standup-digest",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "slack_channel": SLACK_CHANNEL,
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_standup(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RunResponse(
        commits=result.commits,
        issues=result.issues,
        digest=result.digest,
        slack_sent=result.slack_sent,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Standup Digest",
            slug="recipe-21-standup-digest",
            tagline="GitHub + Linear activity summarized for standup.",
            endpoints=[
        ("POST", "/run?dry_run=1", "Generate standup digest.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

