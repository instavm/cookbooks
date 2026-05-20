from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent
from agent import load_kpi_history
from lib.config import GITHUB_REPO

app = FastAPI(title="Investor Update Assembler")


class RunResponse(BaseModel):
    month: str
    mrr_usd: float
    commits: int
    prs_merged: int
    update: str
    headline: str
    history_months: int
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-06-investor-update-assembler",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "github_repo": GITHUB_REPO,
    }


@app.post("/run", response_model=RunResponse)
def run(dry_run: bool = False) -> RunResponse:
    try:
        result = agent.run_assemble(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RunResponse(
        month=result.month,
        mrr_usd=result.mrr_usd,
        commits=result.commits,
        prs_merged=result.prs_merged,
        update=result.update,
        headline=result.headline,
        history_months=result.history_months,
        dry_run=result.dry_run,
    )


@app.get("/history")
def history() -> JSONResponse:
    return JSONResponse({"entries": load_kpi_history()})


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Investor Update Assembler",
            slug="recipe-06-investor-update-assembler",
            tagline="Stripe + GitHub metrics assembled into a monthly investor update.",
            endpoints=[
        ("POST", "/run?dry_run=1", "Assemble update without LLM."),
        ("GET", "/history", "Prior updates on volume.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

