from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, HttpUrl

import agent

app = FastAPI(title="Substack Distribution")


class PublishRequest(BaseModel):
    url: HttpUrl


class PublishResponse(BaseModel):
    url: str
    title: str
    linkedin: str
    x_thread: str
    already_distributed: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-07-substack-distribution",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/publish", response_model=PublishResponse)
def publish(body: PublishRequest, dry_run: bool = False) -> PublishResponse:
    try:
        result = agent.run_publish(str(body.url), dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PublishResponse(
        url=result.url,
        title=result.title,
        linkedin=result.linkedin,
        x_thread=result.x_thread,
        already_distributed=result.already_distributed,
        dry_run=result.dry_run,
    )


@app.get("/preview", response_class=HTMLResponse)
def preview() -> HTMLResponse:
    return HTMLResponse(agent.read_preview_html())


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Substack Distribution",
            slug="recipe-07-substack-distribution",
            tagline="Substack post rewritten for LinkedIn and X with staged preview.",
            endpoints=[
        ("POST", "/publish?dry_run=1", "Scrape URL and generate variants."),
        ("GET", "/preview", "Review distribution copy before posting.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

