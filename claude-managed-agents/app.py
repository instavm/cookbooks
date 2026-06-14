"""FastAPI orchestrator for self-hosting Claude Managed Agents on InstaVM.

Endpoints
---------
- ``GET  /``         Landing page.
- ``GET  /health``   Liveness/readiness probe.
- ``POST /webhook``  Anthropic CMA webhook receiver (session.status_run_started).
- ``GET  /workers``  Inspect the active per-session worker microVMs.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from lib.secrets import VAULT_PLACEHOLDERS, vault_credential
from lib.ui import landing_page
from orchestrator.config import TRIGGER_EVENT, load_worker_config
from orchestrator.dispatcher import Dispatcher
from orchestrator.signature import WebhookError, extract_session_event, verify_and_parse
from orchestrator.worker_pool import WorkerPool

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
_log = logging.getLogger("cma.orchestrator")

WEBHOOK_PATH = "/webhook"


def create_app(*, pool: WorkerPool | None = None, dispatcher: Dispatcher | None = None) -> FastAPI:
    config = load_worker_config()
    if pool is None:
        pool = WorkerPool(config, instavm_api_key=vault_credential("INSTAVM_API_KEY"))
    if dispatcher is None:
        dispatcher = Dispatcher(pool)

    app = FastAPI(title="Claude Managed Agents — InstaVM Sandbox")
    app.state.pool = pool
    app.state.dispatcher = dispatcher

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "ok": "true",
            "slug": "claude-managed-agents",
            "trigger_event": TRIGGER_EVENT,
            "environment_id": config.environment_id or "unset",
            "active_workers": str(pool.count_active()),
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(landing_page(webhook_path=WEBHOOK_PATH, worker_count=pool.count_active()))

    @app.get("/workers")
    def workers() -> JSONResponse:
        return JSONResponse({"workers": pool.list_workers()})

    @app.post(WEBHOOK_PATH)
    async def webhook(request: Request) -> JSONResponse:
        body = await request.body()
        signing_key = vault_credential("ANTHROPIC_WEBHOOK_SIGNING_KEY")
        try:
            payload = verify_and_parse(body, request.headers, signing_key)
        except WebhookError as exc:
            placeholder = VAULT_PLACEHOLDERS["ANTHROPIC_WEBHOOK_SIGNING_KEY"]
            if "not configured" in str(exc) or signing_key == placeholder:
                return JSONResponse({"error": str(exc)}, status_code=503)
            return JSONResponse({"error": str(exc)}, status_code=401)

        event_type, session_id = extract_session_event(payload)
        if event_type != TRIGGER_EVENT:
            _log.info("ignoring event %s", event_type or "<unknown>")
            return JSONResponse({"ok": True, "ignored": event_type})
        if not session_id:
            return JSONResponse({"error": "missing session id"}, status_code=400)

        _log.info("scheduling worker for session %s", session_id)
        dispatcher.schedule(session_id)
        return JSONResponse({"ok": True, "scheduled": session_id})

    return app


app = create_app()
