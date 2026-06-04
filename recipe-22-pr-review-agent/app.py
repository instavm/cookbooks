from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from lib.webhooks import enforce_github_signature

app = FastAPI(title="PR Review Agent")
_log = logging.getLogger(__name__)


class ReviewResponse(BaseModel):
    pr_number: int
    title: str
    review_markdown: str
    verdict: str
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-22-pr-review-agent",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/webhook/github", response_model=ReviewResponse)
async def webhook_github(request: Request, dry_run: bool = False) -> ReviewResponse:
    body_bytes = await request.body()
    enforce_github_signature(body_bytes, request.headers.get("X-Hub-Signature-256"))

    try:
        payload = json.loads(body_bytes)
        result = agent.review_pr(payload, dry_run=dry_run)
    except HTTPException:
        raise
    except Exception:
        _log.exception("webhook_github failed")
        raise HTTPException(status_code=502, detail="upstream error")
    return ReviewResponse(
        pr_number=result.pr_number,
        title=result.title,
        review_markdown=result.review_markdown,
        verdict=result.verdict,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="PR Review Agent",
            slug="recipe-22-pr-review-agent",
            tagline="GitHub PR webhook to structured review comment.",
            endpoints=[
                ("POST", "/webhook/github", "GitHub pull_request payload."),
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )
