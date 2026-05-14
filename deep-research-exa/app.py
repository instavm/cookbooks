"""Deep Research — OpenAI Agents SDK + Exa, with vault-injected credentials.

The agent has two tools:
  * exa_search        — Exa /search with content-snippets
  * exa_get_contents  — Exa /contents for the full readable text of a URL

Both the OpenAI and Exa keys live in the InstaVM org vault and are
substituted at egress (api.openai.com / api.exa.ai). This process never
sees the real values — it ships with placeholder strings that the
platform's MITM proxy rewrites on the wire.
"""
from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import json
import logging
import os
import re
import socket
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx
from agents import Agent, RunConfig, Runner, function_tool
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("deep_research")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-5.5")
MAX_AGENT_TURNS = int(os.environ.get("RESEARCH_MAX_TURNS", "12"))
DEFAULT_SEARCH_RESULTS = int(os.environ.get("RESEARCH_SEARCH_RESULTS", "6"))
PER_PAGE_CHAR_BUDGET = int(os.environ.get("RESEARCH_PAGE_CHARS", "10000"))
MAX_VISITS_PER_REQUEST = int(os.environ.get("RESEARCH_MAX_VISITS", "8"))
MAX_SEARCHES_PER_REQUEST = int(os.environ.get("RESEARCH_MAX_SEARCHES", "10"))
EXA_TIMEOUT_S = float(os.environ.get("EXA_TIMEOUT_S", "30"))

OPENAI_PLACEHOLDER = os.environ.get("OPENAI_PLACEHOLDER", "OPENAI_KEY")
EXA_PLACEHOLDER = os.environ.get("EXA_PLACEHOLDER", "EXA_KEY")
EXA_BASE = "https://api.exa.ai"


# ---------------------------------------------------------------------------
# Per-request scratchpad
# ---------------------------------------------------------------------------


class RequestState:
    def __init__(self, queue: asyncio.Queue[bytes]):
        self.queue = queue
        self.searches: list[str] = []
        self.visits: list[dict[str, Any]] = []
        self.visit_count = 0
        self.search_count = 0
        self.exa_client: httpx.AsyncClient | None = None


_request_state: contextvars.ContextVar[RequestState | None] = contextvars.ContextVar(
    "deep_research_state", default=None,
)


def _sse(event: str, data: Any) -> bytes:
    body = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


def _phase(phase_id: str, status: str, **extra: Any) -> bytes:
    payload: dict[str, Any] = {"id": phase_id, "status": status}
    payload.update(extra)
    return _sse("phase", payload)


async def _emit(event: bytes) -> None:
    state = _request_state.get()
    if state is not None:
        await state.queue.put(event)


def _env_ready() -> None:
    # OpenAI Agents SDK reads OPENAI_API_KEY directly. Set the placeholder so
    # the SDK doesn't refuse to start; egress rewrites it on the wire. Don't
    # clobber a real key if one is already in the env (local-dev convenience).
    existing = os.environ.get("OPENAI_API_KEY", "").strip()
    if not existing or existing == OPENAI_PLACEHOLDER:
        os.environ["OPENAI_API_KEY"] = OPENAI_PLACEHOLDER
        return
    if existing.startswith("sk-"):
        logger.info("OPENAI_API_KEY already set (real key); leaving as-is for local dev.")
    else:
        logger.warning(
            "OPENAI_API_KEY is set to a non-placeholder, non-sk value; leaving as-is. "
            "Egress rewriting expects the placeholder %r; unexpected values may break upstream calls.",
            OPENAI_PLACEHOLDER,
        )


# ---------------------------------------------------------------------------
# Exa client (uses placeholder; egress proxy substitutes the real key)
# ---------------------------------------------------------------------------


async def _exa_post_with_client(
    client: httpx.AsyncClient,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    # Retry transient DNS / connection failures: the InstaVM egress allowlist
    # is applied after the service starts, so the first lookup can hit a
    # negative-cached "Temporary failure in name resolution" before the
    # resolver warms up.
    last_exc: Exception | None = None
    for attempt in range(8):
        try:
            resp = await client.post(f"{EXA_BASE}{path}", headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Exa {path} {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        except RuntimeError:
            raise
        except (
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
            httpx.RemoteProtocolError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            socket.gaierror,
        ) as exc:
            last_exc = exc
            await asyncio.sleep(min(2.0 * (attempt + 1), 8.0))
    raise RuntimeError(f"Exa {path} failed after retries: {last_exc!s}")


async def _exa_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "x-api-key": EXA_PLACEHOLDER,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    state = _request_state.get()
    # Tools are only invoked from inside a request, so a per-request client
    # should always be set. Raise loudly otherwise so accidental top-level
    # invocations surface immediately instead of silently leaking a client.
    if state is None or state.exa_client is None:
        raise RuntimeError("exa client not initialized for this request")
    return await _exa_post_with_client(state.exa_client, path, payload, headers)


async def _warm_dns() -> None:
    loop = asyncio.get_event_loop()
    for host in ("api.exa.ai", "api.openai.com"):
        for attempt in range(20):
            try:
                await loop.getaddrinfo(host, 443)
                logger.info("dns warm: %s ok (attempt %d)", host, attempt + 1)
                break
            except Exception as exc:
                logger.info("dns warm: %s pending (%s)", host, exc)
                await asyncio.sleep(2.0)


# ---------------------------------------------------------------------------
# Tools exposed to the agent
# ---------------------------------------------------------------------------


@function_tool
async def exa_search(query: str, max_results: int = DEFAULT_SEARCH_RESULTS) -> list[dict[str, str]]:
    """Search the public web with Exa. Returns up to `max_results` rows.

    Each row contains: title, url, snippet (short text excerpt), published_date.
    Use this to discover sources; follow up with `exa_get_contents` to read the
    full text of any URL that looks promising.
    """
    query = query.strip()[:500]
    state = _request_state.get()
    if state is None:
        raise RuntimeError("exa_search called outside of a request context")
    if state.search_count >= MAX_SEARCHES_PER_REQUEST:
        await _emit(_sse("tool", {
            "name": "exa_search", "status": "skipped",
            "input": query, "reason": "per-request search cap reached",
        }))
        return []
    state.search_count += 1
    state.searches.append(query)
    await _emit(_sse("tool", {"name": "exa_search", "status": "active", "input": query}))
    try:
        data = await _exa_post(
            "/search",
            {
                "query": query,
                "numResults": max(1, min(int(max_results), 10)),
                "type": "auto",
                "contents": {"text": {"maxCharacters": 600}},
            },
        )
    except Exception as exc:
        logger.exception("exa search failed for %r", query)
        await _emit(_sse("tool", {
            "name": "exa_search", "status": "error",
            "input": query, "error": str(exc)[:300],
        }))
        return []

    rows: list[dict[str, str]] = []
    for r in data.get("results", []) or []:
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip()
        if not url or not title:
            continue
        highlights = r.get("highlights") or []
        highlight = highlights[0] if isinstance(highlights, list) and highlights else ""
        snippet = r.get("text") or highlight or ""
        rows.append({
            "title": title,
            "url": url,
            "snippet": (snippet or "").strip()[:600],
            "published_date": (r.get("publishedDate") or "")[:10],
        })

    await _emit(_sse("tool", {
        "name": "exa_search", "status": "done" if rows else "empty",
        "input": query, "count": len(rows),
    }))
    return rows


@function_tool
async def exa_get_contents(url: str) -> str:
    """Fetch the readable text of a single URL via Exa /contents."""
    url = url.strip()
    state = _request_state.get()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or len(url) > 2048:
        await _emit(_sse("tool", {
            "name": "exa_get_contents", "status": "skipped",
            "input": url[:200], "reason": "unsupported URL",
        }))
        return "(unsupported URL)"
    if state is not None:
        if state.visit_count >= MAX_VISITS_PER_REQUEST:
            await _emit(_sse("tool", {
                "name": "exa_get_contents", "status": "skipped",
                "input": url, "reason": "per-request visit cap reached",
            }))
            return (
                f"(visit cap reached: {state.visit_count} URLs already fetched. "
                "Synthesize from what you have.)"
            )
        state.visit_count += 1
        state.visits.append({"url": url})
        await _emit(_sse("tool", {"name": "exa_get_contents", "status": "active", "input": url}))

    try:
        data = await _exa_post(
            "/contents",
            {"urls": [url], "text": {"maxCharacters": PER_PAGE_CHAR_BUDGET}},
        )
    except Exception as exc:
        logger.exception("exa contents failed for %s", url)
        await _emit(_sse("tool", {
            "name": "exa_get_contents", "status": "error",
            "input": url, "error": str(exc)[:300],
        }))
        return f"(could not fetch {url})"

    results = data.get("results") or []
    if not results:
        await _emit(_sse("tool", {
            "name": "exa_get_contents", "status": "empty", "input": url,
        }))
        return f"(no content for {url})"
    text = (results[0].get("text") or "").strip()[:PER_PAGE_CHAR_BUDGET]
    if state is not None and state.visits:
        state.visits[-1].update({"chars": len(text)})
    await _emit(_sse("tool", {
        "name": "exa_get_contents", "status": "done",
        "input": url, "chars": len(text),
    }))
    return text or f"(empty document at {url})"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def _build_agent() -> Agent:
    return Agent(
        name="deep_research_analyst",
        model=MODEL_NAME,
        instructions=(
            "You are a meticulous research analyst. You have two tools:\n"
            "  * exa_search(query, max_results) — discover relevant URLs.\n"
            "  * exa_get_contents(url) — read the full text of a single URL.\n\n"
            "Workflow:\n"
            "  1. Decompose the user's question into 2-4 focused sub-queries.\n"
            "  2. For each sub-query, call exa_search and pick the 2-3 most\n"
            "     promising URLs.\n"
            "  3. Call exa_get_contents on each promising URL — read the page,\n"
            "     don't rely on the snippet alone.\n"
            "  4. If important gaps remain, do another search round.\n"
            "  5. Stop when you have enough evidence (or after a handful of\n"
            "     rounds).\n\n"
            "Final answer: a markdown briefing with EXACTLY these sections:\n"
            "  - **TL;DR** (2-3 bullets)\n"
            "  - **Key Findings** (5-8 bullets, each citing a URL inline as\n"
            "    `(source: https://...)`)\n"
            "  - **Risks & Counterpoints**\n"
            "  - **Open Questions**\n"
            "  - **Sources** — every URL you actually opened, with a one-line\n"
            "    description.\n\n"
            "Citation rules: every factual claim must cite a URL that actually\n"
            "appeared in a tool result. Don't invent URLs. If two sources\n"
            "disagree, say so."
        ),
        tools=[exa_search, exa_get_contents],
    )


def _friendly_error(exc: Exception) -> str:
    msg = str(exc).strip().lower()
    if any(needle in msg for needle in ("api key", "unauthorized", "401", "incorrect api key")):
        return (
            "Upstream rejected the request. Verify the org vault has bindings "
            "for both api.openai.com (credential OPENAI_KEY) and api.exa.ai "
            "(credential EXA_KEY)."
        )
    if "timeout" in msg or "timed out" in msg:
        return "An upstream call timed out. Try again."
    if "exa /search 4" in msg or "exa /contents 4" in msg:
        return "Exa rejected the request. Verify the EXA_KEY binding in the vault."
    return f"Research run failed: {str(exc)[:240]}"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    _env_ready()
    # Resolve upstream hosts in the background so the first user request can
    # proceed without waiting for the egress allowlist to propagate.
    dns_task = asyncio.create_task(_warm_dns())
    try:
        yield
    finally:
        dns_task.cancel()
        try:
            await dns_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("DNS warm-up task failed")


app = FastAPI(title="Deep Research (OpenAI Agents + Exa)", lifespan=_lifespan)


_STATIC_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)


class SecurityHeadersMiddleware:
    """ASGI middleware that injects security headers without buffering the body.

    BaseHTTPMiddleware (which ``@app.middleware('http')`` produces) collects the
    response body before forwarding it, which breaks Server-Sent Events. This
    plain ASGI wrapper preserves streaming by mutating headers in-place on the
    ``http.response.start`` message and otherwise forwarding ``send`` events
    unchanged.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}
                for name, value in _STATIC_SECURITY_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                if b"content-security-policy" not in existing:
                    headers.append((b"content-security-policy", CSP_HEADER.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeadersMiddleware)


class ReportRequest(BaseModel):
    query: str


def _csp_hash(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def _compute_inline_hashes(html: str) -> tuple[str, str]:
    style_matches = re.findall(r"<style\b[^>]*>(.*?)</style>", html, re.DOTALL | re.IGNORECASE)
    script_matches = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    if len(style_matches) != 1 or len(script_matches) != 1:
        raise RuntimeError(
            "expected exactly one inline <style> and one inline <script> block; "
            f"found {len(style_matches)} style and {len(script_matches)} script"
        )
    return _csp_hash(style_matches[0]), _csp_hash(script_matches[0])


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Deep Research · OpenAI Agents + Exa</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <style>
      :root {
        --bg: #0c0d10;
        --panel: #14161b;
        --panel-2: #1a1d24;
        --ink: #f1efe9;
        --ink-soft: #c8c4b8;
        --muted: #7d7a72;
        --rule: #2a2d35;
        --accent: #e8c167;
        --error: #ef6f6f;
        --ok: #7fd1a5;
      }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      html, body { background: var(--bg); color: var(--ink); }
      body {
        font-family: "Inter", system-ui, -apple-system, sans-serif;
        font-size: 15px; line-height: 1.55;
        min-height: 100vh;
      }
      main { max-width: 1180px; margin: 0 auto; padding: 2.2rem 1.5rem 4rem; }
      header.top {
        display: flex; align-items: flex-end; justify-content: space-between;
        gap: 1rem; padding-bottom: 1rem; border-bottom: 1px solid var(--rule);
        margin-bottom: 1.4rem; flex-wrap: wrap;
      }
      .title h1 {
        font-family: "Instrument Serif", "Times New Roman", serif;
        font-weight: 400; font-size: clamp(2rem, 4.4vw, 3rem);
        letter-spacing: -0.01em; line-height: 1.05;
      }
      .title h1 em { color: var(--accent); font-style: italic; }
      .title .sub {
        margin-top: 0.35rem; color: var(--muted);
        font-size: 0.88rem; max-width: 560px;
      }
      .pills { display: flex; gap: 0.4rem; flex-wrap: wrap; }
      .pill {
        font-family: "JetBrains Mono", monospace;
        font-size: 0.7rem; letter-spacing: 0.04em;
        padding: 0.25rem 0.55rem; border: 1px solid var(--rule);
        border-radius: 999px; color: var(--ink-soft);
      }
      .pill.ok { color: var(--ok); border-color: rgba(127,209,165,0.4); }
      .pill.warn { color: var(--error); border-color: rgba(239,111,111,0.45); }

      .panel {
        background: var(--panel);
        border: 1px solid var(--rule);
        border-radius: 12px;
        padding: 1.1rem 1.2rem;
      }

      .composer label {
        display: block;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.7rem; letter-spacing: 0.14em;
        text-transform: uppercase; color: var(--muted);
        margin-bottom: 0.45rem;
      }
      textarea {
        width: 100%; min-height: 110px;
        background: var(--panel-2);
        border: 1px solid var(--rule);
        border-radius: 8px;
        padding: 0.75rem 0.9rem;
        font: inherit; font-size: 0.98rem; line-height: 1.5;
        color: var(--ink); resize: vertical;
        outline: none;
      }
      textarea:focus { border-color: var(--accent); }
      .examples { margin-top: 0.6rem; display: flex; gap: 0.4rem; flex-wrap: wrap; }
      .example {
        font: inherit; font-family: "JetBrains Mono", monospace;
        background: transparent; color: var(--ink-soft);
        border: 1px solid var(--rule); border-radius: 999px;
        padding: 0.28rem 0.7rem; font-size: 0.73rem;
        cursor: pointer; letter-spacing: 0.02em;
      }
      .example:hover { background: var(--panel-2); color: var(--ink); border-color: var(--accent); }

      .controls {
        display: flex; align-items: center; gap: 0.8rem;
        margin-top: 0.9rem; flex-wrap: wrap;
      }
      button.primary {
        cursor: pointer;
        font: inherit; font-weight: 600;
        font-size: 0.95rem;
        background: var(--accent); color: #1a1607;
        border: none; border-radius: 8px;
        padding: 0.6rem 1.1rem;
      }
      button.primary:hover:not(:disabled) { filter: brightness(1.08); }
      button.primary:disabled { opacity: 0.45; cursor: not-allowed; }

      .status {
        font-family: "JetBrains Mono", monospace;
        font-size: 0.78rem; color: var(--ink-soft);
        display: flex; align-items: center; gap: 0.5rem;
      }
      .status.error { color: var(--error); }
      .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); display: none; animation: pulse 1.2s infinite; }
      .dot.active { display: inline-block; }
      @keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.3 } }

      .layout {
        display: grid; gap: 1.1rem; margin-top: 1.2rem;
        grid-template-columns: 1fr;
      }
      @media (min-width: 980px) { .layout { grid-template-columns: 1.6fr 1fr; } }

      .report {
        background: var(--panel);
        border: 1px solid var(--rule);
        border-radius: 12px;
        padding: 1.4rem 1.6rem;
        line-height: 1.65;
        font-size: 0.98rem;
        color: var(--ink);
        white-space: pre-wrap;
        min-height: 240px;
      }
      .report.empty {
        color: var(--muted); font-style: italic;
        display: flex; align-items: center; justify-content: center;
        text-align: center;
      }
      .report .signoff {
        display: block; margin-top: 1.2rem;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.7rem; letter-spacing: 0.08em;
        color: var(--muted); text-align: right;
      }
      .report.pending {
        white-space: normal;
        color: var(--ink);
      }
      .progress-card {
        display: grid;
        gap: 1rem;
      }
      .progress-head {
        display: flex; align-items: center; gap: 0.85rem;
      }
      .radar {
        position: relative;
        width: 44px; height: 44px;
        border: 1px solid rgba(232,193,103,0.35);
        border-radius: 50%;
        background:
          radial-gradient(circle at center, rgba(232,193,103,0.18) 0 3px, transparent 4px),
          radial-gradient(circle at center, transparent 0 14px, rgba(232,193,103,0.08) 15px 16px, transparent 17px);
        overflow: hidden;
        flex: 0 0 auto;
      }
      .radar::before {
        content: "";
        position: absolute; inset: 50% 50% 0 0;
        background: linear-gradient(45deg, rgba(232,193,103,0.5), transparent 70%);
        transform-origin: 100% 0;
        animation: sweep 1.6s linear infinite;
      }
      .radar::after {
        content: "";
        position: absolute; inset: 9px;
        border: 1px solid rgba(232,193,103,0.15);
        border-radius: 50%;
      }
      @keyframes sweep { to { transform: rotate(360deg); } }
      .progress-title {
        font-family: "Instrument Serif", serif;
        font-size: 1.35rem;
        line-height: 1.1;
      }
      .progress-sub {
        color: var(--muted);
        font-family: "JetBrains Mono", monospace;
        font-size: 0.72rem;
        margin-top: 0.18rem;
      }
      .activity {
        border: 1px solid var(--rule);
        border-radius: 10px;
        background: var(--panel-2);
        padding: 0.75rem 0.85rem;
      }
      .activity-label {
        font-family: "JetBrains Mono", monospace;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.64rem;
        margin-bottom: 0.25rem;
      }
      .activity-text {
        color: var(--ink-soft);
        min-height: 1.4rem;
      }
      .steps {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.5rem;
      }
      @media (max-width: 720px) { .steps { grid-template-columns: 1fr 1fr; } }
      .step {
        border: 1px solid var(--rule);
        border-radius: 9px;
        padding: 0.55rem 0.65rem;
        color: var(--muted);
        background: rgba(255,255,255,0.015);
      }
      .step .k {
        display: block;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
      }
      .step .v {
        display: block;
        margin-top: 0.18rem;
        color: var(--ink-soft);
        font-size: 0.86rem;
      }
      .step.active {
        border-color: rgba(232,193,103,0.55);
        box-shadow: 0 0 0 1px rgba(232,193,103,0.08) inset;
      }
      .step.done {
        border-color: rgba(127,209,165,0.35);
      }
      .step.done .k { color: var(--ok); }
      .step.active .k { color: var(--accent); }
      .stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.5rem;
      }
      @media (max-width: 720px) { .stats { grid-template-columns: 1fr 1fr; } }
      .stat {
        background: var(--panel-2);
        border: 1px solid var(--rule);
        border-radius: 9px;
        padding: 0.55rem 0.65rem;
      }
      .stat b {
        display: block;
        font-family: "JetBrains Mono", monospace;
        font-size: 1rem;
        color: var(--accent);
      }
      .stat span {
        color: var(--muted);
        font-size: 0.72rem;
      }

      aside.notebook {
        background: var(--panel);
        border: 1px solid var(--rule);
        border-radius: 12px;
        padding: 1rem 1.1rem;
        max-height: 640px; overflow-y: auto;
      }
      aside.notebook h2 {
        font-family: "Instrument Serif", serif;
        font-weight: 400; font-size: 1.15rem;
        margin-bottom: 0.6rem; color: var(--ink);
        border-bottom: 1px solid var(--rule); padding-bottom: 0.4rem;
      }
      .row {
        display: grid; grid-template-columns: 1.2rem 1fr;
        gap: 0.5rem; padding: 0.45rem 0;
        border-bottom: 1px dashed var(--rule);
        font-size: 0.86rem;
      }
      .row:last-child { border-bottom: none; }
      .glyph { font-family: "JetBrains Mono", monospace; font-size: 0.78rem; color: var(--accent); }
      .row.error .glyph { color: var(--error); }
      .row.skipped .glyph { color: var(--muted); }
      .row .body { color: var(--ink-soft); word-break: break-word; }
      .meta {
        display: block; margin-top: 0.15rem;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.7rem; color: var(--muted);
      }
      a { color: var(--ink); text-decoration: underline; text-decoration-color: var(--rule); }
      a:hover { text-decoration-color: var(--accent); }

      footer {
        margin-top: 2rem; padding-top: 1rem;
        border-top: 1px solid var(--rule);
        color: var(--muted); font-size: 0.78rem;
        font-family: "JetBrains Mono", monospace;
        text-align: center;
      }
      footer code { color: var(--ink-soft); }
    </style>
  </head>
  <body>
    <main>
      <header class="top">
        <div class="title">
          <h1>Deep <em>research</em>, on demand.</h1>
          <div class="sub">An OpenAI Agents SDK analyst that uses Exa to search and read the web — credentials are vault-injected at egress, never in this VM.</div>
        </div>
        <div class="pills">
          <span class="pill" id="model-pill">model · …</span>
          <span class="pill" id="exa-pill">exa · …</span>
          <span class="pill" id="openai-pill">openai · …</span>
        </div>
      </header>

      <section class="panel composer">
        <label for="query">Research brief</label>
        <textarea id="query">What are the most credible 2026 predictions about agentic browser usage at consumer scale? Include funding rounds, product launches, and the major open problems.</textarea>
        <div class="examples">
          <button class="example" data-prompt="Compare Firecracker microVMs to gVisor and Kata Containers across isolation strength, cold-start latency, and ecosystem maturity. Cite primary sources.">microVM isolation</button>
          <button class="example" data-prompt="Summarize the strongest empirical findings on prompt-injection mitigations in 2026. Cite the original papers or blog posts.">prompt injection</button>
          <button class="example" data-prompt="Compare MCP, OpenAI tools, and Anthropic computer-use API. Strengths, weaknesses, ecosystem.">MCP vs tools vs CUA</button>
        </div>
        <div class="controls">
          <button id="run" class="primary">Run research</button>
          <span class="status"><span class="dot" id="dot"></span><span id="status">Idle.</span></span>
        </div>
      </section>

      <section class="layout">
        <article class="report empty" id="report">No report yet. Submit a brief above — the agent will plan sub-queries, search with Exa, read the most promising pages, and file a cited briefing.</article>
        <aside class="notebook">
          <h2>Agent trace</h2>
          <div id="ledger">
            <div class="row skipped"><span class="glyph">·</span><span class="body">Each tool call (exa_search / exa_get_contents) will appear here in real time.</span></div>
          </div>
        </aside>
      </section>

      <footer>
        <code>openai-agents · exa · instavm vault</code>
      </footer>
    </main>
    <script>
      const queryEl = document.getElementById("query");
      const statusEl = document.getElementById("status");
      const statusWrap = statusEl.parentElement;
      const dotEl = document.getElementById("dot");
      const reportEl = document.getElementById("report");
      const ledgerEl = document.getElementById("ledger");
      const runBtn = document.getElementById("run");
      const modelPill = document.getElementById("model-pill");
      const exaPill = document.getElementById("exa-pill");
      const openaiPill = document.getElementById("openai-pill");
      let runState = null;

      function escapeHtml(s) {
        return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
      }
      function shortUrl(u) {
        try {
          const parsed = new URL(u);
          const path = parsed.pathname + parsed.search;
          return parsed.host.replace(/^www\\./, "") + (path.length > 1 ? path.slice(0, 30) + (path.length > 30 ? "…" : "") : "");
        } catch (_) { return String(u).slice(0, 60); }
      }
      function safeHref(u) {
        try {
          const parsed = new URL(u);
          if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
        } catch (_) {}
        return "#";
      }
      function pill(el, label, level) {
        el.textContent = label;
        el.classList.remove("ok", "warn");
        if (level) el.classList.add(level);
      }
      function setStatus(text, level) {
        statusEl.textContent = text;
        statusWrap.classList.toggle("error", level === "error");
      }
      function stopTimer() {
        if (runState && runState.timer) clearInterval(runState.timer);
        if (runState) runState.timer = null;
      }
      function elapsedSeconds() {
        return runState ? Math.max(0, Math.floor((Date.now() - runState.startedAt) / 1000)) : 0;
      }
      function setActivity(text) {
        if (runState) runState.activity = text;
        const el = document.getElementById("activity-text");
        if (el) el.textContent = text;
      }
      function updateStats() {
        if (!runState) return;
        const values = {
          "stat-time": `${elapsedSeconds()}s`,
          "stat-searches": runState.searches,
          "stat-results": runState.results,
          "stat-pages": runState.pages,
        };
        for (const [id, value] of Object.entries(values)) {
          const el = document.getElementById(id);
          if (el) el.textContent = value;
        }
      }
      function markStep(id, state) {
        const el = document.getElementById(`step-${id}`);
        if (!el) return;
        el.classList.remove("active", "done");
        if (state) el.classList.add(state);
      }
      function renderProgress(query) {
        runState = {
          startedAt: Date.now(),
          timer: null,
          searches: 0,
          results: 0,
          pages: 0,
          activity: "Opening an SSE stream and preparing the research agent…",
        };
        reportEl.classList.remove("empty");
        reportEl.classList.add("pending");
        reportEl.innerHTML = `
          <div class="progress-card" aria-live="polite">
            <div class="progress-head">
              <div class="radar" aria-hidden="true"></div>
              <div>
                <div class="progress-title">Research in motion</div>
                <div class="progress-sub">brief · ${escapeHtml(query.slice(0, 96))}${query.length > 96 ? "…" : ""}</div>
              </div>
            </div>
            <div class="activity">
              <div class="activity-label">Now</div>
              <div class="activity-text" id="activity-text">${escapeHtml(runState.activity)}</div>
            </div>
            <div class="steps">
              <div class="step active" id="step-plan"><span class="k">Plan</span><span class="v">split prompt</span></div>
              <div class="step" id="step-search"><span class="k">Search</span><span class="v">query Exa</span></div>
              <div class="step" id="step-read"><span class="k">Read</span><span class="v">inspect sources</span></div>
              <div class="step" id="step-write"><span class="k">Write</span><span class="v">compose brief</span></div>
            </div>
            <div class="stats">
              <div class="stat"><b id="stat-time">0s</b><span>elapsed</span></div>
              <div class="stat"><b id="stat-searches">0</b><span>searches</span></div>
              <div class="stat"><b id="stat-results">0</b><span>results</span></div>
              <div class="stat"><b id="stat-pages">0</b><span>pages read</span></div>
            </div>
          </div>`;
        runState.timer = setInterval(() => {
          updateStats();
          if (!statusWrap.classList.contains("error")) {
            setStatus(`${runState.activity} · ${elapsedSeconds()}s`);
          }
        }, 1000);
      }
      function clearLedger() { ledgerEl.innerHTML = ""; }
      function append({ glyph, body, meta, kind }) {
        const row = document.createElement("div");
        row.className = "row" + (kind ? " " + kind : "");
        row.innerHTML = `<span class="glyph">${escapeHtml(glyph || "·")}</span><span class="body">${body || ""}${meta ? `<span class=\\"meta\\">${meta}</span>` : ""}</span>`;
        ledgerEl.appendChild(row);
        ledgerEl.scrollTop = ledgerEl.scrollHeight;
      }

      async function loadHealth() {
        try {
          const r = await fetch("/health");
          const info = await r.json();
          pill(modelPill, `model · ${info.model || "?"}`, "ok");
          pill(exaPill, `exa · ${info.exa_host || "api.exa.ai"}`, "ok");
          pill(openaiPill, `openai · ${info.openai_host || "api.openai.com"}`, "ok");
        } catch (_) {
          pill(modelPill, "model · ?", "warn");
        }
      }
      loadHealth();

      function handleEvent(event, data) {
        if (event === "phase") {
          if (data.id === "research" && data.status === "active") {
            markStep("plan", "active");
            setActivity("Planning sub-queries and choosing sources…");
            setStatus("Planning sub-queries…");
          }
          if (data.id === "research" && data.status === "done") {
            markStep("search", "done");
            markStep("read", "done");
          }
          if (data.id === "synthesize" && data.status === "active") {
            markStep("write", "active");
            setActivity("Composing the cited briefing…");
            setStatus("Composing the briefing…");
          }
          if (data.id === "synthesize" && data.status === "done") {
            markStep("write", "done");
            stopTimer();
            setStatus(`Done — ${data.searches || 0} searches, ${data.visits || 0} reads.`);
            updateStats();
          }
          return;
        }
        if (event === "tool") {
          const isSearch = data.name === "exa_search";
          if (data.status === "active") {
            if (isSearch) {
              markStep("plan", "done");
              markStep("search", "active");
              setActivity(`Searching Exa for “${data.input}”`);
              setStatus(`Searching: ${data.input}`);
              append({ glyph: "Q", body: `<strong>exa_search</strong> · ${escapeHtml(data.input)}` });
            } else {
              markStep("search", "done");
              markStep("read", "active");
              setActivity(`Reading ${shortUrl(data.input)}`);
              setStatus(`Reading: ${shortUrl(data.input)}`);
              append({ glyph: "▸", body: `<strong>read</strong> · <a href="${escapeHtml(safeHref(data.input))}" target="_blank" rel="noopener">${escapeHtml(shortUrl(data.input))}</a>` });
            }
          } else if (data.status === "done") {
            if (isSearch) {
              if (runState) {
                runState.searches += 1;
                runState.results += Number(data.count || 0);
              }
              append({ glyph: "✓", body: `Found ${data.count} hits for <em>${escapeHtml(data.input)}</em>` });
            } else {
              if (runState) runState.pages += 1;
              append({ glyph: "✓", body: `Read <a href="${escapeHtml(safeHref(data.input))}" target="_blank" rel="noopener">${escapeHtml(shortUrl(data.input))}</a>`, meta: `${(data.chars||0).toLocaleString()} chars` });
            }
            updateStats();
          } else if (data.status === "empty") {
            if (isSearch && runState) runState.searches += 1;
            updateStats();
            append({ glyph: "∅", body: `No results for <em>${escapeHtml(data.input || "")}</em>`, kind: "skipped" });
          } else if (data.status === "skipped") {
            append({ glyph: "—", body: `Skipped`, meta: escapeHtml(data.reason || ""), kind: "skipped" });
          } else if (data.status === "error") {
            append({ glyph: "!", body: `Tool error · ${escapeHtml(data.error || "")}`, kind: "error" });
          }
          return;
        }
        if (event === "report") {
          stopTimer();
          reportEl.classList.remove("empty");
          reportEl.classList.remove("pending");
          reportEl.innerHTML = `${escapeHtml(data.text || "(empty report)")}<span class="signoff">— deep_research_analyst · openai-agents · exa</span>`;
          return;
        }
        if (event === "error") {
          stopTimer();
          append({ glyph: "✕", body: escapeHtml(data.message || "error"), kind: "error" });
          setStatus(data.message || "failed", "error");
          return;
        }
      }

      async function submit() {
        const q = queryEl.value.trim();
        if (!q) return;
        runBtn.disabled = true;
        clearLedger();
        renderProgress(q);
        append({ glyph: "↗", body: "Starting research run", meta: escapeHtml(new Date().toLocaleTimeString()) });
        setStatus("Starting…");
        dotEl.classList.add("active");

        let resp;
        try {
          resp = await fetch("/api/report", {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify({ query: q }),
          });
        } catch (err) {
          stopTimer();
          setStatus(String(err), "error");
          dotEl.classList.remove("active");
          runBtn.disabled = false;
          return;
        }
        if (!resp.ok || !resp.body) {
          stopTimer();
          let msg = `HTTP ${resp.status}`;
          try { const j = await resp.json(); if (j && j.detail) msg = j.detail; } catch (_) {}
          setStatus(msg, "error");
          append({ glyph: "✕", body: escapeHtml(msg), kind: "error" });
          dotEl.classList.remove("active");
          runBtn.disabled = false;
          return;
        }
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\\n\\n")) !== -1) {
            const chunk = buf.slice(0, i);
            buf = buf.slice(i + 2);
            const lines = chunk.split("\\n");
            let event = "message"; const dataLines = [];
            for (const ln of lines) {
              if (ln.startsWith("event: ")) event = ln.slice(7).trim();
              else if (ln.startsWith("data: ")) dataLines.push(ln.slice(6));
            }
            if (!dataLines.length) continue;
            let payload = dataLines.join("\\n");
            try { payload = JSON.parse(payload); } catch (_) {}
            handleEvent(event, payload);
          }
        }
        dotEl.classList.remove("active");
        stopTimer();
        updateStats();
        runBtn.disabled = false;
      }
      runBtn.addEventListener("click", submit);
      queryEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
      });
      document.querySelectorAll(".example").forEach((btn) => {
        btn.addEventListener("click", () => {
          const prompt = btn.getAttribute("data-prompt");
          if (prompt) {
            queryEl.value = prompt;
            queryEl.focus();
          }
        });
      });
    </script>
  </body>
</html>
"""


_STYLE_HASH, _SCRIPT_HASH = _compute_inline_hashes(HTML)
CSP_HEADER = (
    "default-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self' https://fonts.gstatic.com; "
    f"style-src 'self' {_STYLE_HASH} https://fonts.googleapis.com; "
    f"script-src 'self' {_SCRIPT_HASH}; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "form-action 'self'"
)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model": MODEL_NAME,
        "openai_host": "api.openai.com",
        "exa_host": "api.exa.ai",
        "vault_mode": True,
    }


async def _research_stream(query: str) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    state = RequestState(queue)
    token = _request_state.set(state)

    async def _runner() -> None:
        try:
            await queue.put(_phase("research", "active"))
            await queue.put(_sse("config", {"model": MODEL_NAME, "max_turns": MAX_AGENT_TURNS}))
            agent = _build_agent()
            started = time.monotonic()
            async with httpx.AsyncClient(timeout=EXA_TIMEOUT_S) as client:
                state.exa_client = client
                result = await Runner.run(
                    agent,
                    f"Research prompt: {query}",
                    run_config=RunConfig(workflow_name="deep-research-exa"),
                    max_turns=MAX_AGENT_TURNS,
                )
            elapsed = time.monotonic() - started
            briefing = (result.final_output or "").strip() if result else ""
            await queue.put(_phase("research", "done", duration_s=round(elapsed, 1)))
            await queue.put(_phase("synthesize", "active"))
            await queue.put(_sse("report", {"text": briefing or "(empty briefing)"}))
            await queue.put(_phase(
                "synthesize", "done",
                searches=len(state.searches), visits=state.visit_count,
            ))
        except Exception as exc:
            logger.exception("research run failed")
            await queue.put(_sse("error", {"message": _friendly_error(exc)}))
        finally:
            await queue.put(b"__DONE__")

    runner_task = asyncio.create_task(_runner())

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                if not runner_task.done():
                    yield b": ping\n\n"
                    continue
                break
            if event == b"__DONE__":
                break
            yield event
    finally:
        runner_task.cancel()
        try:
            await runner_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("research runner cleanup failed")
        _request_state.reset(token)


@app.post("/api/report")
async def create_report(request: ReportRequest) -> StreamingResponse:
    query = (request.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required.")
    if len(query) > 4000:
        raise HTTPException(status_code=413, detail="Query exceeds 4000 characters.")
    return StreamingResponse(
        _research_stream(query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
