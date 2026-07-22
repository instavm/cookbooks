"""InstaVM Preview — product API + polished static UI."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import asyncio

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from . import config
from . import ops_registry
from .attachments import parse_attachments
from .build import build_stream, iterate_stream, validate_keys, with_heartbeats
from .intent import classify_intent
from .local_secrets import apply_local_secrets
from .ops import extract_ops, looks_like_ops, ops_stream
from .plan import generate_plan, normalize_plan
from .sessions import store
from .templates_data import get_template, list_ops_examples, list_templates

logger = logging.getLogger("instavm_preview")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
GUEST_COOKIE = "ivm_preview_guest"

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    loaded = apply_local_secrets()
    if loaded["instavm"] or loaded["openai"]:
        logger.info(
            "Local secrets applied (instavm=%s openai=%s)",
            loaded["instavm"],
            loaded["openai"],
        )
    yield
    for session in await store.all_sessions():
        try:
            if session.cleanup_task and not session.cleanup_task.done():
                session.cleanup_task.cancel()
            await session.client.delete(session.sandbox)
        except Exception:
            logger.exception("failed to clean up sandbox on shutdown")


app = FastAPI(title=config.PRODUCT_NAME, lifespan=_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _static_no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


class AttachmentIn(BaseModel):
    name: str = Field(default="reference.png", max_length=120)
    mime_type: Optional[str] = Field(default=None, max_length=64)
    data_base64: Optional[str] = None
    data_url: Optional[str] = None


class PlanTodoIn(BaseModel):
    id: str = Field(default="t1", max_length=32)
    title: str = Field(default="", max_length=160)


class PlanIn(BaseModel):
    summary: str = Field(default="", max_length=500)
    todos: list[PlanTodoIn] = Field(default_factory=list)


class PlanRequest(BaseModel):
    prompt: str = Field(default="", max_length=config.MAX_PROMPT_CHARS)
    template_id: Optional[str] = None
    guest_id: Optional[str] = None
    feedback: Optional[str] = Field(default=None, max_length=2000)
    previous: Optional[PlanIn] = None
    attachments: list[AttachmentIn] = Field(default_factory=list)
    session_id: Optional[str] = None
    vm_id: Optional[str] = None
    has_ops_context: bool = False


class BuildRequest(BaseModel):
    prompt: str = Field(default="", max_length=config.MAX_PROMPT_CHARS)
    template_id: Optional[str] = None
    guest_id: Optional[str] = None
    attachments: list[AttachmentIn] = Field(default_factory=list)
    plan: Optional[PlanIn] = None


class IterateRequest(BaseModel):
    session_id: str
    instruction: str = Field(default="", max_length=config.MAX_PROMPT_CHARS)
    guest_id: Optional[str] = None
    attachments: list[AttachmentIn] = Field(default_factory=list)


def _guest_id_from(request: Request, body_guest: str | None) -> str:
    if body_guest and body_guest.strip():
        return body_guest.strip()[:64]
    cookie = request.cookies.get(GUEST_COOKIE)
    if cookie:
        return cookie[:64]
    return store.new_guest_id()


def _set_guest_cookie(response: Response, guest_id: str) -> None:
    response.set_cookie(
        GUEST_COOKIE,
        guest_id,
        max_age=60 * 60 * 24 * 30,
        httponly=False,
        samesite="lax",
        secure=os.environ.get("PREVIEW_COOKIE_SECURE", "").lower() in ("1", "true"),
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "product": config.PRODUCT_NAME,
        "runtime": "openai-agents-sandbox",
        "model": config.MODEL_NAME,
    }


@app.get("/api/config")
async def public_config() -> dict[str, Any]:
    return {
        "product_name": config.PRODUCT_NAME,
        "signup_url": config.SIGNUP_URL,
        "billing_url": config.BILLING_URL,
        "dash_url": config.DASH_URL,
        "model": config.MODEL_NAME,
        "guest_builds_per_day": config.GUEST_BUILDS_PER_DAY,
        "guest_iterates_per_session": config.GUEST_ITERATES_PER_SESSION,
        "preview_ttl_seconds": config.PREVIEW_TTL_SECONDS,
        "max_attachments": config.MAX_ATTACHMENTS,
        "max_attachment_bytes": config.MAX_ATTACHMENT_BYTES,
        "allowed_attachment_mimes": sorted(config.ALLOWED_ATTACHMENT_MIMES),
        "posthog_key": config.POSTHOG_KEY,
        "posthog_host": config.POSTHOG_HOST,
    }


@app.get("/api/templates")
async def templates() -> dict[str, Any]:
    return {
        "templates": list_templates(),
        "ops_examples": list_ops_examples(),
    }


@app.get("/api/guest")
async def guest_status(request: Request) -> Response:
    guest_id = _guest_id_from(request, None)
    status = await store.guest_status(guest_id)
    payload = {**status, "signup_url": config.SIGNUP_URL, "billing_url": config.BILLING_URL}
    # Return JSON via Response so we can set cookie
    import json

    response = Response(content=json.dumps(payload), media_type="application/json")
    _set_guest_cookie(response, guest_id)
    return response


@app.get("/api/session/{session_id}")
async def get_session(session_id: str, request: Request) -> dict[str, Any]:
    guest_id = _guest_id_from(request, None)
    payload = await store.remix_payload(session_id, guest_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    # Remix is public-read for viral loop; iterate still checks guest ownership.
    return payload


@app.post("/api/plan")
@limiter.limit("30/minute")
async def plan(request: Request, body: PlanRequest) -> dict[str, Any]:
    """Web-app plan — or route InstaVM client ops (no fake web app)."""
    try:
        validate_keys()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        attachments = parse_attachments(
            [a.model_dump(exclude_none=True) for a in body.attachments]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prompt = (body.prompt or "").strip()
    if body.template_id:
        tmpl = get_template(body.template_id)
        if tmpl is None:
            raise HTTPException(status_code=404, detail="Unknown template.")
        if not prompt:
            prompt = tmpl["prompt"]
    if not prompt and attachments:
        prompt = config.DEFAULT_VISION_PROMPT
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail="Prompt is required (or attach a screenshot).",
        )

    guest_id = _guest_id_from(request, body.guest_id)
    has_ops_ctx = bool(
        body.has_ops_context or body.session_id or body.vm_id
    )

    if (
        not attachments
        and looks_like_ops(prompt, has_ops_context=has_ops_ctx)
        and classify_intent(prompt, has_ops_context=has_ops_ctx) == "ops"
    ):
        try:
            ops = await extract_ops(
                prompt,
                context={
                    "session_id": body.session_id,
                    "vm_id": body.vm_id,
                },
            )
        except Exception as exc:
            logger.exception("ops extract failed")
            raise HTTPException(
                status_code=502, detail=f"Ops parse failed: {exc!s}"[:400]
            ) from exc
        resp = JSONResponse({**ops, "mode": "ops", "guest_id": guest_id})
        _set_guest_cookie(resp, guest_id)
        return resp

    previous = None
    if body.previous is not None:
        previous = normalize_plan(body.previous.model_dump())

    try:
        result = await generate_plan(
            prompt,
            feedback=body.feedback,
            previous=previous,
            has_attachments=bool(attachments),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("plan generation failed")
        raise HTTPException(
            status_code=502, detail=f"Plan failed: {exc!s}"[:400]
        ) from exc

    out = {**result, "mode": "webapp", "guest_id": guest_id}
    resp = JSONResponse(out)
    _set_guest_cookie(resp, guest_id)
    return resp


class OpsRequest(BaseModel):
    prompt: str = Field(default="", max_length=config.MAX_PROMPT_CHARS)
    guest_id: Optional[str] = None
    session_id: Optional[str] = None
    vm_id: Optional[str] = None


@app.post("/api/ops")
@limiter.limit("20/minute")
async def ops(request: Request, body: OpsRequest) -> Response:
    """Run InstaVM client actions directly (SSE) — no web-app build."""
    try:
        validate_keys()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    prompt = (body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")
    has_ops_ctx = bool(body.session_id or body.vm_id)
    if not looks_like_ops(prompt, has_ops_context=has_ops_ctx):
        raise HTTPException(
            status_code=400,
            detail="Not an InstaVM client operation. Use Build for web apps.",
        )

    guest_id = _guest_id_from(request, body.guest_id)
    stream = StreamingResponse(
        with_heartbeats(
            ops_stream(
                prompt,
                guest_id,
                session_id=body.session_id,
                vm_id=body.vm_id,
            )
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    _set_guest_cookie(stream, guest_id)
    return stream


@app.websocket("/ws/pty/{token}")
async def pty_proxy(websocket: WebSocket, token: str) -> None:
    """Browser ↔ InstaVM PTY relay (API key stays on the server)."""
    guest_id = websocket.cookies.get(GUEST_COOKIE) or ""
    entry = ops_registry.get(token, guest_id=guest_id or None)
    if entry is None and guest_id:
        # Cookie may lag on first connect; allow token-only if guest matches later
        entry = ops_registry.get(token)
        if entry and entry.get("guest_id") and entry["guest_id"] != guest_id:
            entry = None
    if entry is None:
        entry = ops_registry.get(token)
    if entry is None:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    upstream_url = entry["upstream_ws"]
    try:
        import websockets
    except ImportError:
        await websocket.close(code=1011)
        return

    try:
        async with websockets.connect(
            upstream_url,
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:

            async def client_to_upstream() -> None:
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg.get("type") == "websocket.disconnect":
                            break
                        if "bytes" in msg and msg["bytes"] is not None:
                            await upstream.send(msg["bytes"])
                        elif "text" in msg and msg["text"] is not None:
                            await upstream.send(msg["text"])
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client() -> None:
                try:
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(str(message))
                except Exception:
                    pass

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc:
                    logger.debug("pty proxy task ended: %s", exc)
    except Exception:
        logger.exception("pty proxy failed")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@app.post("/api/build")
@limiter.limit("20/minute")
async def build(request: Request, body: BuildRequest) -> Response:
    try:
        validate_keys()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        attachments = parse_attachments(
            [a.model_dump(exclude_none=True) for a in body.attachments]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prompt = (body.prompt or "").strip()
    template_id = body.template_id
    if template_id:
        tmpl = get_template(template_id)
        if tmpl is None:
            raise HTTPException(status_code=404, detail="Unknown template.")
        if not prompt:
            prompt = tmpl["prompt"]

    if not prompt and attachments:
        prompt = config.DEFAULT_VISION_PROMPT
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail="Prompt is required (or attach a screenshot).",
        )
    if len(prompt) > config.MAX_PROMPT_CHARS:
        raise HTTPException(status_code=413, detail="Prompt too long.")

    plan = normalize_plan(body.plan.model_dump()) if body.plan else None

    guest_id = _guest_id_from(request, body.guest_id)
    try:
        await store.check_guest_build_quota(guest_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    stream = StreamingResponse(
        with_heartbeats(
            build_stream(
                prompt,
                guest_id,
                template_id,
                attachments=attachments,
                plan=plan,
            )
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    _set_guest_cookie(stream, guest_id)
    return stream


@app.post("/api/iterate")
@limiter.limit("30/minute")
async def iterate(request: Request, body: IterateRequest) -> Response:
    try:
        validate_keys()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        attachments = parse_attachments(
            [a.model_dump(exclude_none=True) for a in body.attachments]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    instruction = (body.instruction or "").strip()
    if not instruction and attachments:
        instruction = (
            "Restyle the app to closely match the attached screenshot(s)."
        )
    if not instruction:
        raise HTTPException(
            status_code=400,
            detail="Instruction is required (or attach a screenshot).",
        )
    if not body.session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required.")

    guest_id = _guest_id_from(request, body.guest_id)
    stream = StreamingResponse(
        with_heartbeats(
            iterate_stream(
                body.session_id.strip(),
                instruction,
                guest_id,
                attachments=attachments,
            )
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    _set_guest_cookie(stream, guest_id)
    return stream


@app.get("/")
async def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="UI not built.")
    return FileResponse(
        index_path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
