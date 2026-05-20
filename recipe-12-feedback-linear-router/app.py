from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from lib.secrets import vault_credential
from lib.webhooks import verify_slack_signature, webhook_verify_enabled

app = FastAPI(title="Feedback Linear Router")


class RouteResponse(BaseModel):
    ref_id: str
    text: str
    category: str
    routed: bool
    issue_id: str | None = None
    issue_url: str | None = None
    dry_run: bool
    skipped: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-12-feedback-linear-router",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/webhook/slack")
async def slack_webhook(request: Request, dry_run: bool = False) -> Any:
    body_bytes = await request.body()
    if webhook_verify_enabled() and not dry_run:
        secret = vault_credential("SLACK_SIGNING_SECRET")
        if secret and secret != "SLACK_SIGNING_SECRET":
            sig = request.headers.get("X-Slack-Signature")
            ts = request.headers.get("X-Slack-Request-Timestamp")
            if not verify_slack_signature(body_bytes, ts, sig, secret):
                raise HTTPException(status_code=401, detail="Invalid Slack signature")

    try:
        body = json.loads(body_bytes)
        result = agent.handle_slack_event(body, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if isinstance(result, dict):
        return result

    return RouteResponse(
        ref_id=result.ref_id,
        text=result.text,
        category=result.category,
        routed=result.routed,
        issue_id=result.issue.id if result.issue else None,
        issue_url=result.issue.url if result.issue else None,
        dry_run=result.dry_run,
        skipped=result.skipped,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Feedback Linear Router",
            slug="recipe-12-feedback-linear-router",
            tagline="Slack feedback classified and routed to Linear issues.",
            endpoints=[
                ("POST", "/webhook/slack", "Slack event payload."),
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )
