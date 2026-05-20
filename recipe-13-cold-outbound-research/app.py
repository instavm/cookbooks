import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent
from lib.config import DIGEST_TO

app = FastAPI(title="Cold Outbound Research")


class ProspectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    company: str = Field(..., min_length=1)
    domain: str = ""


class ProspectResponse(BaseModel):
    company: str
    email: str
    research_hits: int
    subject: str
    body: str
    mail_sent: bool
    skipped: bool
    dry_run: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-13-cold-outbound-research",
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    }


@app.post("/prospect", response_model=ProspectResponse)
def prospect(body: ProspectRequest, dry_run: bool = False) -> ProspectResponse:
    try:
        result = agent.research_and_email(
            name=body.name,
            email=str(body.email),
            company=body.company,
            domain=body.domain,
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ProspectResponse(
        company=result.company,
        email=result.email,
        research_hits=result.research_hits,
        subject=result.subject,
        body=result.body,
        mail_sent=result.mail_sent,
        skipped=result.skipped,
        dry_run=result.dry_run,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Cold Outbound Research",
            slug="recipe-13-cold-outbound-research",
            tagline="Prospect research to personalized outbound email.",
            endpoints=[
        ("POST", "/prospect?dry_run=1", "Research prospect JSON.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

