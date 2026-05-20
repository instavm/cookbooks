from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent

app = FastAPI(title="SEO Blog Pipeline")


class TopicRequest(BaseModel):
    topic: str = Field(..., min_length=3)


class TopicResponse(BaseModel):
    topic: str
    draft: dict
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-16-seo-blog-pipeline",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/topic", response_model=TopicResponse)
def topic(body: TopicRequest, dry_run: bool = False) -> TopicResponse:
    try:
        result = agent.generate_blog(body.topic, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TopicResponse(topic=result.topic, draft=result.draft, dry_run=result.dry_run)


@app.get("/preview", response_model=None)
def preview(format: str = "html"):
    draft = agent.load_preview()
    if not draft:
        raise HTTPException(status_code=404, detail="No draft yet — POST /topic first")
    if format == "json":
        return JSONResponse(draft)
    html = agent.render_preview_html(draft)
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="SEO Blog Pipeline",
            slug="recipe-16-seo-blog-pipeline",
            tagline="Topic to SEO-optimized draft with editorial preview.",
            endpoints=[
        ("POST", "/topic?dry_run=1", "Generate draft."),
        ("GET", "/preview", "HTML preview.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

