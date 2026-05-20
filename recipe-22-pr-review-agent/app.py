from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from lib.config import sample_pr_path
from lib.secrets import vault_credential
from lib.webhooks import verify_github_signature, webhook_verify_enabled

app = FastAPI(title="PR Review Agent")


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
    if webhook_verify_enabled() and not dry_run:
        secret = vault_credential("GITHUB_WEBHOOK_SECRET")
        if secret and secret != "GITHUB_WEBHOOK_SECRET":
            sig = request.headers.get("X-Hub-Signature-256")
            if not verify_github_signature(body_bytes, sig, secret):
                raise HTTPException(status_code=401, detail="Invalid GitHub signature")

    try:
        payload = json.loads(body_bytes)
        result = agent.review_pr(payload, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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
