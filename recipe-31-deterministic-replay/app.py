from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel

import agent

app = FastAPI(title="Deterministic Replay")


class ReplayResponse(BaseModel):
    content: str
    deterministic: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {"ok": "true", "slug": "recipe-31-deterministic-replay", "cassette": "fixtures/cassette.jsonl"}


@app.post("/replay", response_model=ReplayResponse)
def replay() -> ReplayResponse:
    try:
        result = agent.run_replay()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReplayResponse(content=result.content, deterministic=result.deterministic)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Deterministic Replay",
            slug="recipe-31-deterministic-replay",
            tagline="Deterministic LLM replay from offline cassette tapes.",
            endpoints=[
        ("POST", "/replay", "Replay recorded LLM response.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

