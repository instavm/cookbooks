from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from lib.ui import landing_page
from pydantic import BaseModel, Field

import agent
from lib.config import DEFAULT_TASKS, PARALLEL_CHILDREN
from lib.secrets import secret_available

app = FastAPI(title="Browser Snapshot Fork")


class ForkRequest(BaseModel):
    tasks: list[str] = Field(default_factory=lambda: list(DEFAULT_TASKS))
    snapshot_id: str | None = None


class ChildEcho(BaseModel):
    task: str
    stdout: str
    exit_code: int


class ForkResponse(BaseModel):
    children: list[ChildEcho]
    snapshot_id: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-28-browser-snapshot-fork",
        "instavm_configured": "true" if secret_available("INSTAVM_API_KEY") else "false",
        "parallel_children": str(PARALLEL_CHILDREN),
    }


@app.post("/fork", response_model=ForkResponse)
async def fork(body: ForkRequest | None = None) -> ForkResponse:
    payload = body or ForkRequest()
    try:
        result = await agent.run_fork(
            tasks=payload.tasks[:PARALLEL_CHILDREN],
            snapshot_id=payload.snapshot_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ForkResponse(
        children=[
            ChildEcho(task=c.task, stdout=c.stdout, exit_code=c.exit_code) for c in result.children
        ],
        snapshot_id=result.snapshot_id,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        landing_page(
            title="Browser Snapshot Fork",
            slug="recipe-28-browser-snapshot-fork",
            tagline="Fork parallel InstaVM child sandboxes from a shared snapshot.",
            endpoints=[
        ("POST", "/fork", "Spawn parallel child sandbox tasks.")
            ],
            pills=["vault-backed", "egress allowlist"],
        )
    )

