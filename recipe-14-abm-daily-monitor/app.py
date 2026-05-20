from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent
from lib.config import DIGEST_TO

app = FastAPI(title="ABM Daily Monitor")


class AccountsRequest(BaseModel):
    accounts: list[str] = Field(default_factory=list, min_length=0)


class MonitorResponse(BaseModel):
    accounts_checked: int
    new_signal: int
    digest: str
    mail_sent: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-14-abm-daily-monitor",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/accounts")
def set_accounts(body: AccountsRequest) -> dict[str, object]:
    path = agent.save_accounts(body.accounts)
    return {"saved": len(body.accounts), "path": str(path)}


@app.post("/run", response_model=MonitorResponse)
def run(dry_run: bool = False) -> MonitorResponse:
    try:
        result = agent.run_monitor(dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MonitorResponse(
        accounts_checked=result.accounts_checked,
        new_signal=result.new_signal,
        digest=result.digest,
        mail_sent=result.mail_sent,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="ABM Daily Monitor",
            slug="recipe-14-abm-daily-monitor",
            tagline="Top-account news diff and net-new digest.",
            endpoints=[
        ("POST", "/run?dry_run=1", "Run ABM monitor."),
        ("POST", "/accounts", "Set account list.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

