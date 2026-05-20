from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from lib.config import BRAND_NAME

app = FastAPI(title="Mention Monitor")


class MentionItem(BaseModel):
    id: str
    source: str
    title: str
    url: str
    score: int
    summary: str
    sentiment: str


class PollResponse(BaseModel):
    polled: int
    new: int
    alerted: int
    dry_run: bool
    mentions: list[MentionItem]


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-09-mention-monitor",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "brand": BRAND_NAME,
    }


@app.post("/run", response_model=PollResponse)
def run(dry_run: bool = False) -> PollResponse:
    try:
        result = agent.run_poll(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PollResponse(
        polled=result.polled,
        new=result.new,
        alerted=result.alerted,
        dry_run=result.dry_run,
        mentions=[MentionItem(**m) for m in result.mentions],
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Mention Monitor",
            slug="recipe-09-mention-monitor",
            tagline="Brand mentions across HN and Reddit scored and sent to Slack.",
            endpoints=[
        ("POST", "/run?dry_run=1", "Poll sources and score mentions.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

