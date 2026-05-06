"""Research Desk — deep research over the public web, with vault-injected
credentials.

Architecture in one paragraph:

1. The user's request goes to an OpenAI Agents agent (``deep_research_analyst``)
   that has two tools: ``web_search`` and ``visit_url``.
2. Both tools drive the **InstaVM platform browser** (Chromium running in
   InstaVM cloud) — the orchestrator never opens a TCP socket to the public
   web itself.
3. The orchestrator's ``OPENAI_API_KEY`` is the literal string ``OPENAI_KEY``
   (a placeholder). The real OpenAI credential lives in the org's InstaVM
   vault and the platform's egress proxy substitutes it on the wire.
4. Progress is streamed to the UI over Server-Sent Events: every search and
   page fetch shows up live in the "Editor's Notebook" panel.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import quote_plus, urlparse

import httpx
from agents import Agent, RunConfig, Runner, function_tool
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from instavm import InstaVM

logger = logging.getLogger("research_desk")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("RESEARCH_TIMEOUT_S", "240"))
MAX_AGENT_TURNS = int(os.environ.get("RESEARCH_MAX_TURNS", "16"))
DEFAULT_SEARCH_RESULTS = int(os.environ.get("RESEARCH_SEARCH_RESULTS", "6"))
PER_PAGE_CHAR_BUDGET = int(os.environ.get("RESEARCH_PAGE_CHARS", "12000"))
BROWSER_NAVIGATE_TIMEOUT_MS = int(os.environ.get("RESEARCH_BROWSER_TIMEOUT_MS", "25000"))
BROWSER_RESULTS_WAIT_MS = int(os.environ.get("RESEARCH_BROWSER_WAIT_MS", "8000"))
HTTP_TIMEOUT_S = float(os.environ.get("RESEARCH_HTTP_TIMEOUT_S", "20"))
MAX_VISITS_PER_REQUEST = int(os.environ.get("RESEARCH_MAX_VISITS", "8"))

# Vault knobs — match the vault-demo cookbook's defaults so a single
# org-wide vault setup serves every InstaVM cookbook.
VAULT_PLACEHOLDER = os.environ.get("VAULT_DEMO_PLACEHOLDER", "OPENAI_KEY")
VAULT_TARGET_HOST = os.environ.get("VAULT_DEMO_HOST", "api.openai.com")
INSTAVM_API_BASE = os.environ.get("INSTAVM_API_BASE", "https://api.instavm.io").rstrip("/")


def _looks_like_real_openai_key(value: str) -> bool:
    v = (value or "").strip()
    return v.startswith("sk-") and len(v) >= 20


def _looks_like_placeholder_secret(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return True
    return any(
        marker in normalized
        for marker in (
            "dummy", "test", "placeholder",
            "your_key", "your-api-key", "changeme", "example",
        )
    )


# ---------------------------------------------------------------------------
# Per-request scratchpad (carried via ContextVar)
# ---------------------------------------------------------------------------


class RequestState:
    def __init__(self, queue: asyncio.Queue[bytes]):
        self.queue = queue
        self.visits: list[dict[str, Any]] = []
        self.searches: list[str] = []
        self.visit_count = 0
        self.browser_session_id: str | None = None
        self.lock = asyncio.Lock()


_request_state: contextvars.ContextVar[RequestState | None] = contextvars.ContextVar(
    "research_request_state", default=None,
)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Vault preflight (read-only, runs once at startup and on demand)
# ---------------------------------------------------------------------------


class VaultPreflight(BaseModel):
    ok: bool
    vault_id: str | None = None
    vault_name: str | None = None
    credential_name: str | None = None
    message: str
    cli_hint: list[str] | None = None


_preflight_cache: VaultPreflight | None = None


def _vault_get(instavm_key: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
    url = f"{INSTAVM_API_BASE}{path}"
    headers = {"X-API-Key": instavm_key}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


def _list_vaults(instavm_key: str) -> list[dict[str, Any]]:
    payload = _vault_get(instavm_key, "/v1/vaults")
    return payload.get("vaults", []) if isinstance(payload, dict) else []


def _list_vault_services(instavm_key: str, vault_id: str) -> list[dict[str, Any]]:
    payload = _vault_get(instavm_key, f"/v1/vaults/{vault_id}/services")
    return payload.get("services", []) if isinstance(payload, dict) else []


def _run_preflight(instavm_key: str) -> VaultPreflight:
    cli_hint = [
        f'VAULT_ID=$(instavm vault create cookbook-org -j | python3 -c "import sys,json; print(json.load(sys.stdin)[\\"id\\"])")',
        f'instavm vault secret set "$VAULT_ID" {VAULT_PLACEHOLDER}',
        f'instavm vault service add "$VAULT_ID" --host {VAULT_TARGET_HOST} --auth-type bearer --credential {VAULT_PLACEHOLDER}',
        f'instavm vault discover "$VAULT_ID"',
    ]
    try:
        vaults = _list_vaults(instavm_key)
    except Exception as exc:
        return VaultPreflight(
            ok=False,
            message=f"Could not reach the InstaVM vault API: {exc!s}",
            cli_hint=cli_hint,
        )
    if not vaults:
        return VaultPreflight(
            ok=False,
            message=(
                "Your organization has no vaults yet. Run the four CLI commands "
                "below once and every InstaVM cookbook will pick up the OpenAI "
                "key automatically."
            ),
            cli_hint=cli_hint,
        )
    for vault in vaults:
        vault_id = str(vault.get("id") or "")
        if not vault_id:
            continue
        try:
            services = _list_vault_services(instavm_key, vault_id)
        except Exception:
            continue
        for svc in services:
            if not svc.get("enabled", True):
                continue
            host = str(svc.get("host") or svc.get("upstream_host") or "").lower()
            if host != VAULT_TARGET_HOST:
                continue
            auth_cfg = svc.get("auth_config") or {}
            credential = (
                auth_cfg.get("token") or auth_cfg.get("key")
                or auth_cfg.get("credential") or VAULT_PLACEHOLDER
            )
            return VaultPreflight(
                ok=True,
                vault_id=vault_id,
                vault_name=str(vault.get("name") or vault_id),
                credential_name=str(credential),
                message=(
                    f"Vault '{vault.get('name') or vault_id}' has a binding to "
                    f"{VAULT_TARGET_HOST}. The platform substitutes the real "
                    f"key on the wire — this orchestrator never sees it."
                ),
            )
    return VaultPreflight(
        ok=False,
        message=(
            f"None of your {len(vaults)} vault(s) has a service binding to "
            f"{VAULT_TARGET_HOST}. Add one with the CLI commands below."
        ),
        cli_hint=cli_hint,
    )


# ---------------------------------------------------------------------------
# Orchestrator startup checks
# ---------------------------------------------------------------------------


def _validate_orchestrator_env() -> str:
    """Verify the orchestrator is in vault-mode and return INSTAVM_API_KEY."""
    instavm_key = (os.environ.get("INSTAVM_API_KEY") or "").strip()
    if not instavm_key or _looks_like_placeholder_secret(instavm_key):
        raise RuntimeError(
            "INSTAVM_API_KEY is required. The orchestrator needs it both to "
            "drive the platform browser and to query the vault for preflight."
        )

    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if _looks_like_real_openai_key(openai_key):
        raise RuntimeError(
            "OPENAI_API_KEY appears to be a real OpenAI key (starts with "
            "'sk-'). This cookbook is vault-only: the real key should live "
            "in the org InstaVM vault, not in this orchestrator's environment. "
            f"Unset OPENAI_API_KEY or set it to the placeholder name "
            f"({VAULT_PLACEHOLDER!r}) so the egress proxy can substitute "
            "the real value at TLS write time."
        )
    # Force the placeholder so the OpenAI SDK doesn't 401 before egress sees
    # the request. The MITM proxy substitutes the real value on the wire.
    os.environ["OPENAI_API_KEY"] = VAULT_PLACEHOLDER
    return instavm_key


# ---------------------------------------------------------------------------
# InstaVM browser helpers
# ---------------------------------------------------------------------------


_instavm_client: InstaVM | None = None
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _get_instavm_client() -> InstaVM | None:
    global _instavm_client
    if _instavm_client is not None:
        return _instavm_client
    api_key = (os.environ.get("INSTAVM_API_KEY") or "").strip()
    if not api_key or _looks_like_placeholder_secret(api_key):
        return None
    try:
        _instavm_client = InstaVM(api_key=api_key, auto_start_session=False)
    except Exception:
        logger.exception("instavm client init failed")
        _instavm_client = None
    return _instavm_client


async def _ensure_browser_session(client: InstaVM) -> str:
    state = _request_state.get()
    if state is None:
        return await asyncio.to_thread(
            client.create_browser_session, 1280, 800, _BROWSER_USER_AGENT,
        )
    async with state.lock:
        if state.browser_session_id:
            return state.browser_session_id
        session_id = await asyncio.to_thread(
            client.create_browser_session, 1280, 800, _BROWSER_USER_AGENT,
        )
        state.browser_session_id = session_id
        return session_id


def _navigate_and_wait(
    client: InstaVM,
    session_id: str,
    url: str,
    *,
    wait_selector: str | None,
) -> None:
    """Navigate then optionally wait for a CSS selector to render."""
    client.browser_navigate(url, session_id, BROWSER_NAVIGATE_TIMEOUT_MS)
    if wait_selector:
        try:
            client.browser_wait(
                "selector", session_id,
                selector=wait_selector, timeout=BROWSER_RESULTS_WAIT_MS,
            )
        except Exception:
            # Wait failure is non-fatal — extraction may still find results.
            pass


def _extract_bing_results(
    client: InstaVM, session_id: str, max_results: int,
) -> list[dict[str, str]]:
    cites = client.browser_extract_elements(session_id, "li.b_algo cite", None) or []
    titles = client.browser_extract_elements(session_id, "li.b_algo h2", None) or []
    snippets = client.browser_extract_elements(session_id, "li.b_algo .b_caption p", None) or []
    out: list[dict[str, str]] = []
    for i in range(min(len(cites), max_results * 2)):
        url_text = (cites[i].get("text") or "").strip()
        if not url_text:
            continue
        # Bing renders cite as "github.com › firecracker › firecracker"; keep
        # only the host-and-path portion before any " › " breadcrumb.
        url = url_text.split(" › ", 1)[0].strip()
        url = url.split()[0] if url else url
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        title = (titles[i].get("text") or "").strip() if i < len(titles) else ""
        if not title:
            continue
        snippet = (snippets[i].get("text") or "").strip() if i < len(snippets) else ""
        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= max_results:
            break
    return out


def _extract_ddg_results(
    client: InstaVM, session_id: str, max_results: int,
) -> list[dict[str, str]]:
    elements = client.browser_extract_elements(session_id, "a.result__a", ["href"]) or []
    snippets = client.browser_extract_elements(session_id, "a.result__snippet", None) or []
    out: list[dict[str, str]] = []
    for i, el in enumerate(elements[: max_results * 2]):
        href = (el.get("attributes") or {}).get("href") or el.get("href") or ""
        href = _unwrap_ddg_redirect(href)
        title = (el.get("text") or "").strip()
        if not href or not title:
            continue
        out.append({
            "title": title,
            "url": href,
            "snippet": (snippets[i].get("text") or "").strip() if i < len(snippets) else "",
        })
        if len(out) >= max_results:
            break
    return out


def _unwrap_ddg_redirect(href: str) -> str:
    if not href:
        return href
    try:
        parsed = urlparse(href)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            from urllib.parse import parse_qs, unquote
            qs = parse_qs(parsed.query)
            wrapped = (qs.get("uddg") or [""])[0]
            if wrapped:
                return unquote(wrapped)
        if href.startswith("//"):
            return "https:" + href
    except Exception:
        return href
    return href


async def _browser_search(query: str, max_results: int) -> tuple[list[dict[str, str]], str]:
    """Search via the InstaVM browser. Returns (results, transport_used).

    Tries Bing first (wait for ``li.b_algo`` to render), then DDG html.
    Raises if the InstaVM browser isn't configured at all; returns ``([], ...)``
    if both engines render but the selectors don't match (rare).
    """
    client = _get_instavm_client()
    if client is None:
        raise RuntimeError("instavm browser not configured")
    session_id = await _ensure_browser_session(client)

    # Strategy 1: Bing.
    try:
        await asyncio.to_thread(
            _navigate_and_wait, client, session_id,
            f"https://www.bing.com/search?q={quote_plus(query)}",
            wait_selector="li.b_algo cite",
        )
        results = await asyncio.to_thread(
            _extract_bing_results, client, session_id, max_results,
        )
        if results:
            return results, "instavm-browser:bing"
    except Exception as exc:
        logger.warning("bing browser search failed: %s", exc)

    # Strategy 2: DDG html.
    try:
        await asyncio.to_thread(
            _navigate_and_wait, client, session_id,
            f"https://duckduckgo.com/html/?q={quote_plus(query)}",
            wait_selector="a.result__a",
        )
        results = await asyncio.to_thread(
            _extract_ddg_results, client, session_id, max_results,
        )
        return results, "instavm-browser:ddg"
    except Exception as exc:
        logger.warning("ddg browser search failed: %s", exc)
        return [], "instavm-browser:failed"


async def _browser_visit(url: str) -> str:
    client = _get_instavm_client()
    if client is None:
        raise RuntimeError("instavm browser not configured")
    session_id = await _ensure_browser_session(client)
    await asyncio.to_thread(
        _navigate_and_wait, client, session_id, url, wait_selector=None,
    )
    content = await asyncio.to_thread(
        client.browser_extract_content,
        session_id, None, False, False, 0,
    )
    readable = (content or {}).get("readable_content") or {}
    text = (readable.get("content") or readable.get("text") or "").strip()
    if not text:
        body = await asyncio.to_thread(
            client.browser_extract_elements, session_id, "body", None,
        )
        if body:
            text = (body[0].get("text") or "").strip()
    return text[:PER_PAGE_CHAR_BUDGET]


# ---------------------------------------------------------------------------
# Tools exposed to the agent
# ---------------------------------------------------------------------------


@function_tool
async def web_search(query: str, max_results: int = DEFAULT_SEARCH_RESULTS) -> list[dict[str, str]]:
    """Search the public web for ``query`` and return ranked result rows.

    Each row has ``title``, ``url`` and ``snippet`` keys. The orchestrator
    drives the InstaVM platform browser (Chromium) — there is no direct HTTP
    fallback in this cookbook because the orchestrator VM has restricted
    egress.
    """
    state = _request_state.get()
    if state is not None:
        state.searches.append(query)
        await _emit(_sse("tool", {
            "name": "web_search", "status": "active", "input": query,
        }))
    try:
        results, transport = await _browser_search(query, max_results)
    except Exception as exc:
        logger.exception("browser search failed for %r", query)
        await _emit(_sse("tool", {
            "name": "web_search", "status": "error",
            "input": query, "error": str(exc)[:300],
        }))
        return []
    if not results:
        await _emit(_sse("tool", {
            "name": "web_search", "status": "empty",
            "input": query, "transport": transport,
        }))
        return []
    await _emit(_sse("tool", {
        "name": "web_search", "status": "done",
        "input": query, "transport": transport, "count": len(results),
    }))
    return results


@function_tool
async def visit_url(url: str) -> str:
    """Fetch a URL and return its readable text content (article-mode)."""
    state = _request_state.get()
    if state is not None:
        if state.visit_count >= MAX_VISITS_PER_REQUEST:
            await _emit(_sse("tool", {
                "name": "visit_url", "status": "skipped",
                "input": url, "reason": "per-request visit cap reached",
            }))
            return (
                f"(visit cap reached; this request has already fetched "
                f"{state.visit_count} URLs. Synthesize from what you have.)"
            )
        state.visit_count += 1
        state.visits.append({"url": url})
        await _emit(_sse("tool", {
            "name": "visit_url", "status": "active", "input": url,
        }))
    try:
        text = await _browser_visit(url)
    except Exception as exc:
        logger.exception("browser visit failed for %s", url)
        await _emit(_sse("tool", {
            "name": "visit_url", "status": "error",
            "input": url, "error": str(exc)[:300],
        }))
        return f"(could not fetch {url})"
    if state is not None and state.visits:
        state.visits[-1].update({"chars": len(text)})
    await _emit(_sse("tool", {
        "name": "visit_url", "status": "done",
        "input": url, "transport": "instavm-browser", "chars": len(text),
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
            "You are a meticulous research analyst with two tools: web_search "
            "and visit_url. Produce a concise, evidence-backed markdown "
            "briefing on the user's question.\n\n"
            "Workflow:\n"
            "  1. Decompose the question into 2-4 focused sub-queries.\n"
            "  2. For each sub-query call web_search and pick 2-3 promising URLs.\n"
            "  3. Call visit_url on each promising URL — read the page rather "
            "than relying on the snippet alone.\n"
            "  4. If important questions remain, do another search round.\n"
            "  5. Stop when you have enough evidence (or after a handful of "
            "rounds).\n\n"
            "Format the final briefing as markdown with EXACTLY these sections "
            "in this order, no others:\n"
            "  - **TL;DR** (2-3 bullets)\n"
            "  - **Key Findings** (5-8 bullets, each citing a source URL "
            "inline as `(source: https://...)`)\n"
            "  - **Risks & Counterpoints**\n"
            "  - **Open Questions**\n"
            "  - **Sources** — bulleted list of every URL you actually visited, "
            "with a one-line description.\n\n"
            "Citation rules: every factual claim must reference a URL that "
            "actually appeared in a tool result. Don't invent URLs. If two "
            "sources disagree, say so."
        ),
        tools=[web_search, visit_url],
    )


def _friendly_provider_error(exc: Exception) -> str:
    message = str(exc).strip().lower()
    if any(needle in message for needle in (
        "api key", "authentication", "unauthorized",
        "missing authentication", "incorrect api key",
    )):
        return (
            "The OpenAI request was rejected. Verify the org vault has a "
            f"binding to {VAULT_TARGET_HOST} with the {VAULT_PLACEHOLDER} "
            "credential."
        )
    if "timeout" in message or "timed out" in message:
        return "OpenAI took too long to respond. Try again."
    if "server disconnected" in message or "connection" in message:
        return "OpenAI closed the request before returning. Try again."
    return "The research request failed. Verify vault setup and try again."


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _preflight_cache
    instavm_key = _validate_orchestrator_env()
    try:
        _preflight_cache = await asyncio.to_thread(_run_preflight, instavm_key)
    except Exception as exc:
        _preflight_cache = VaultPreflight(
            ok=False, message=f"Preflight crashed: {exc!s}",
        )
    if _preflight_cache.ok:
        logger.info("vault preflight ok: %s", _preflight_cache.message)
    else:
        logger.warning("vault preflight failed: %s", _preflight_cache.message)
    try:
        yield
    finally:
        global _instavm_client
        _instavm_client = None


app = FastAPI(title="The Research Desk", lifespan=_lifespan)


class ReportRequest(BaseModel):
    query: str


# UI is deliberately a flat HTML literal so the cookbook ships as a single
# python file. Newspaper aesthetic: serif type, cream paper, ruled lines, no
# glassmorphism.
HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>The Research Desk</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <style>
      :root {
        --paper: #f4ecdb;
        --paper-deep: #ece2cc;
        --ink: #111111;
        --ink-soft: #2a2a2a;
        --muted: #6f6a5e;
        --rule: #1a1a1a;
        --highlight: #b48a2c;
        --error: #8b1a1a;
      }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      html, body { background: var(--paper); color: var(--ink); }
      body {
        font-family: "Source Serif 4", Georgia, "Times New Roman", serif;
        font-size: 17px;
        line-height: 1.55;
        background-image:
          radial-gradient(rgba(0,0,0,0.025) 1px, transparent 1px);
        background-size: 3px 3px;
        min-height: 100vh;
      }
      main { max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
      .masthead { text-align: center; padding: 0.6rem 0 0.4rem; border-top: 4px double var(--rule); border-bottom: 4px double var(--rule); margin-bottom: 0.6rem; }
      .masthead .nameplate {
        font-family: "Playfair Display", "Times New Roman", serif;
        font-weight: 900;
        font-size: clamp(2rem, 6vw, 3.6rem);
        letter-spacing: 0.04em;
        line-height: 1.05;
        text-transform: uppercase;
      }
      .masthead .latin { font-style: italic; color: var(--muted); font-size: 0.85rem; letter-spacing: 0.06em; margin-top: 0.2rem; }
      .dateline {
        display: flex; justify-content: space-between; align-items: baseline;
        font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em;
        color: var(--muted); padding: 0.4rem 0; border-bottom: 1px solid var(--rule);
        margin-bottom: 1.2rem;
      }
      .dateline .pill { padding: 0.1rem 0.5rem; border: 1px solid var(--rule); border-radius: 0; }
      .dateline .pill.warn { color: var(--error); border-color: var(--error); }
      .dateline .pill.ok { color: var(--ink); }

      .lede {
        text-align: center;
        font-family: "Playfair Display", serif;
        font-size: clamp(1.6rem, 3.5vw, 2.2rem);
        font-weight: 700;
        line-height: 1.18;
        margin: 0.8rem auto 0.4rem; max-width: 760px;
      }
      .deck {
        text-align: center;
        font-style: italic; color: var(--ink-soft);
        max-width: 720px; margin: 0 auto 1.2rem;
        font-size: 0.95rem;
      }

      .panel {
        background: var(--paper-deep);
        border: 1px solid var(--rule);
        padding: 1rem 1.1rem;
        margin: 1rem 0;
      }
      .panel h2 {
        font-family: "Playfair Display", serif; font-weight: 700;
        font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.18em;
        margin-bottom: 0.6rem; color: var(--ink);
        border-bottom: 1px solid var(--rule); padding-bottom: 0.4rem;
      }

      .form-row label {
        display: block;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.7rem; letter-spacing: 0.14em;
        text-transform: uppercase; color: var(--muted);
        margin-bottom: 0.3rem;
      }
      textarea {
        width: 100%; min-height: 100px;
        background: var(--paper);
        border: 1px solid var(--rule);
        padding: 0.7rem 0.85rem;
        font: inherit; font-size: 1rem;
        line-height: 1.45;
        color: var(--ink); resize: vertical;
        outline: none;
      }
      textarea:focus { border-color: var(--highlight); box-shadow: inset 0 0 0 1px var(--highlight); }
      .examples { margin-top: 0.55rem; display: flex; gap: 0.4rem; flex-wrap: wrap; }
      .example {
        font: inherit; font-family: "JetBrains Mono", monospace;
        background: transparent; color: var(--ink);
        border: 1px solid var(--rule); border-radius: 0;
        padding: 0.25rem 0.6rem; font-size: 0.74rem;
        cursor: pointer; letter-spacing: 0.04em;
      }
      .example:hover { background: var(--ink); color: var(--paper); }
      button.primary {
        margin-top: 0.85rem; cursor: pointer;
        font: inherit; font-family: "Playfair Display", serif; font-weight: 700;
        font-size: 1rem; letter-spacing: 0.05em; text-transform: uppercase;
        background: var(--ink); color: var(--paper);
        border: 1px solid var(--rule); border-radius: 0;
        padding: 0.55rem 1.2rem;
      }
      button.primary:hover:not(:disabled) { background: var(--paper); color: var(--ink); }
      button.primary:disabled { opacity: 0.4; cursor: not-allowed; }

      .status-bar {
        display: flex; align-items: center; gap: 0.7rem; min-height: 1.2rem;
        margin-top: 0.6rem;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.78rem; color: var(--ink-soft);
      }
      .status-bar.error { color: var(--error); }
      .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--ink); display: none; animation: pulse 1.4s infinite; }
      .pulse.active { display: inline-block; }
      @keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.3 } }

      .layout { display: grid; gap: 1.1rem; margin-top: 1rem; grid-template-columns: 1fr; }
      @media (min-width: 950px) { .layout { grid-template-columns: 1.55fr 1fr; } }

      .briefing {
        background: var(--paper);
        border: 1px solid var(--rule);
        padding: 1.4rem 1.6rem;
        white-space: pre-wrap;
        line-height: 1.62;
        font-size: 1.01rem;
        color: var(--ink);
      }
      .briefing.empty {
        color: var(--muted); font-style: italic;
        text-align: center;
      }
      .briefing .signoff {
        display: block; margin-top: 1rem;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.72rem; letter-spacing: 0.12em;
        color: var(--muted);
        text-transform: uppercase; text-align: right;
      }

      .notebook {
        background: var(--paper);
        border: 1px solid var(--rule);
        padding: 1rem 1.1rem;
        max-height: 600px; overflow-y: auto;
      }
      .notebook .head {
        font-family: "Playfair Display", serif;
        font-weight: 700; font-size: 0.85rem;
        text-transform: uppercase; letter-spacing: 0.18em;
        margin-bottom: 0.7rem;
        border-bottom: 1px solid var(--rule); padding-bottom: 0.4rem;
      }
      .ledger { display: flex; flex-direction: column; gap: 0.7rem; }
      .ledger-row {
        display: grid; grid-template-columns: 1.4rem 1fr;
        gap: 0.5rem; font-size: 0.85rem; line-height: 1.45;
      }
      .ledger-row .glyph {
        font-family: "JetBrains Mono", monospace;
        font-size: 0.78rem;
        font-weight: 700;
        color: var(--ink);
      }
      .ledger-row.error .glyph { color: var(--error); }
      .ledger-row.skipped .glyph { color: var(--muted); }
      .ledger-row .body { color: var(--ink-soft); }
      .ledger-row .meta {
        font-family: "JetBrains Mono", monospace;
        font-size: 0.74rem; color: var(--muted);
        display: block; margin-top: 0.1rem;
      }
      .ledger-row a { color: var(--ink); text-decoration: underline; }
      .ledger-row a:hover { color: var(--highlight); }

      .vault-banner {
        margin: 1rem 0;
        background: var(--paper-deep);
        border: 1px solid var(--error);
        padding: 1rem 1.1rem;
      }
      .vault-banner h3 {
        font-family: "Playfair Display", serif;
        font-weight: 700; font-size: 0.85rem; letter-spacing: 0.16em;
        text-transform: uppercase; color: var(--error);
        margin-bottom: 0.5rem;
      }
      .vault-banner p { margin-bottom: 0.6rem; color: var(--ink); }
      .vault-banner pre {
        font-family: "JetBrains Mono", monospace;
        background: var(--ink); color: var(--paper);
        padding: 0.7rem 0.85rem;
        font-size: 0.75rem; overflow-x: auto;
        white-space: pre;
      }

      .ornament { text-align: center; color: var(--muted); margin: 1rem 0; letter-spacing: 1rem; }
    </style>
  </head>
  <body>
    <main>
      <header class="masthead">
        <div class="nameplate">The Research Desk</div>
        <div class="latin">— Vol. I · Filed via InstaVM Platform Browser —</div>
      </header>
      <div class="dateline">
        <span id="dateline-date">…</span>
        <span class="pill ok" id="model-pill">Model · …</span>
        <span class="pill ok" id="browser-pill">Browser · …</span>
        <span class="pill" id="vault-pill">Vault · …</span>
      </div>

      <h1 class="lede">A research analyst that does the reading for you.</h1>
      <p class="deck">Type a question. The agent searches the public web, opens the most promising results, reads them through a real Chromium running in InstaVM's cloud, and files a memo with citations.</p>

      <div id="vault-banner"></div>

      <section class="panel">
        <div class="form-row">
          <label for="query">Editor's Brief</label>
          <textarea id="query">Summarize the latest AI browser-agent landscape: leading products, what they automate, the headline open problems, and which startups closed funding in the last 12 months.</textarea>
          <div class="examples">
            <button class="example" data-prompt="Compare Firecracker microVMs to gVisor and Kata Containers across isolation strength, cold-start, and ecosystem maturity.">microVM isolation</button>
            <button class="example" data-prompt="What are the strongest empirical findings about prompt-injection mitigation in 2026? Cite the relevant papers.">prompt injection 2026</button>
            <button class="example" data-prompt="Explain the difference between MCP, OpenAI tools, and the Anthropic computer-use API. Strengths and weaknesses of each.">MCP vs tools vs CUA</button>
          </div>
          <button id="run" class="primary">File the report</button>
          <div class="status-bar"><span class="pulse" id="dot"></span><span id="status">Awaiting brief.</span></div>
        </div>
      </section>

      <div class="ornament">§ § §</div>

      <section class="layout">
        <article class="panel">
          <h2>Filed Report</h2>
          <div id="report" class="briefing empty">No story has been filed yet. Submit a brief above and the agent will go to press.</div>
        </article>
        <aside class="notebook">
          <div class="head">Editor's Notebook</div>
          <div id="ledger" class="ledger">
            <div class="ledger-row skipped"><span class="glyph">·</span><span class="body">Each search and page fetch will appear here as the agent works.</span></div>
          </div>
        </aside>
      </section>

      <div class="ornament">— end of page one —</div>
    </main>
    <script>
      const queryEl = document.getElementById("query");
      const statusEl = document.getElementById("status");
      const statusBar = statusEl.parentElement;
      const dotEl = document.getElementById("dot");
      const reportEl = document.getElementById("report");
      const ledgerEl = document.getElementById("ledger");
      const runBtn = document.getElementById("run");
      const modelPill = document.getElementById("model-pill");
      const browserPill = document.getElementById("browser-pill");
      const vaultPill = document.getElementById("vault-pill");
      const vaultBanner = document.getElementById("vault-banner");
      const datelineDate = document.getElementById("dateline-date");

      datelineDate.textContent = new Date().toLocaleDateString(undefined, {
        weekday: "long", year: "numeric", month: "long", day: "numeric",
      }).toUpperCase();

      document.querySelectorAll(".example").forEach((btn) => {
        btn.addEventListener("click", () => {
          queryEl.value = btn.dataset.prompt;
          queryEl.focus();
        });
      });

      function escapeHtml(value) {
        return String(value)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }
      function shortHost(url) {
        try { const u = new URL(url); return u.host.replace(/^www\\./, ""); } catch { return url.slice(0, 40); }
      }
      function shortUrl(url) {
        try {
          const u = new URL(url);
          const path = u.pathname + u.search;
          return u.host.replace(/^www\\./, "") + (path.length > 1 ? path.slice(0, 36) + (path.length > 36 ? "…" : "") : "");
        } catch { return url.slice(0, 60); }
      }

      function pill(el, text, level) {
        el.textContent = text;
        el.classList.remove("warn", "ok");
        if (level) el.classList.add(level);
      }

      async function loadHealth() {
        try {
          const r = await fetch("/health"); const info = await r.json();
          if (info.model) pill(modelPill, `Model · ${info.model}`, "ok");
          if (info.browser) pill(browserPill, `Browser · ${info.browser === "instavm" ? "InstaVM" : "fallback only"}`, info.browser === "instavm" ? "ok" : "warn");
        } catch (_) {}
      }
      async function loadVault() {
        try {
          const r = await fetch("/api/preflight"); const info = await r.json();
          if (info.ok) {
            pill(vaultPill, `Vault · ${info.vault_name || "ok"}`, "ok");
            vaultBanner.innerHTML = "";
          } else {
            pill(vaultPill, "Vault · MISSING", "warn");
            renderVaultBanner(info);
          }
        } catch (_) {
          pill(vaultPill, "Vault · ?", "warn");
        }
      }
      function renderVaultBanner(info) {
        const cmds = (info.cli_hint || []).map((c) => escapeHtml(c)).join("\\n");
        vaultBanner.innerHTML = `
          <div class="vault-banner">
            <h3>Vault not configured</h3>
            <p>${escapeHtml(info.message || "")}</p>
            <p>Run these four CLI commands once on your machine — every InstaVM cookbook will then pick up the OpenAI key automatically; you don't have to paste it into any deploy form:</p>
            <pre>${cmds}</pre>
          </div>`;
      }

      loadHealth();
      loadVault();

      function setStatus(text, level) {
        statusEl.textContent = text;
        statusBar.classList.toggle("error", level === "error");
      }

      function appendLedger({ glyph, body, meta, kind }) {
        const row = document.createElement("div");
        row.className = "ledger-row" + (kind ? " " + kind : "");
        row.innerHTML = `<span class="glyph">${escapeHtml(glyph || "·")}</span><span class="body">${body || ""}${meta ? `<span class=\\"meta\\">${meta}</span>` : ""}</span>`;
        ledgerEl.appendChild(row);
        ledgerEl.scrollTop = ledgerEl.scrollHeight;
        return row;
      }
      function clearLedger() { ledgerEl.innerHTML = ""; }

      function handleEvent(event, data) {
        if (event === "phase") {
          if (data.id === "research" && data.status === "active") {
            setStatus("Editor consulting the wires…");
          } else if (data.id === "synthesize" && data.status === "active") {
            setStatus("Composing the memo…");
          } else if (data.id === "synthesize" && data.status === "done") {
            setStatus(`Filed in ${data.searches || 0} searches and ${data.visits || 0} reads.`);
          }
          return;
        }
        if (event === "tool") {
          const isSearch = data.name === "web_search";
          if (data.status === "active") {
            if (isSearch) {
              setStatus(`Searching: ${data.input}`);
              appendLedger({ glyph: "Q", body: `Searching the wires for <em>${escapeHtml(data.input)}</em>` });
            } else {
              setStatus(`Reading: ${shortHost(data.input)}`);
              appendLedger({ glyph: "▣", body: `Reading <a href="${escapeHtml(data.input)}" target="_blank" rel="noopener">${escapeHtml(shortUrl(data.input))}</a>` });
            }
          } else if (data.status === "done") {
            if (isSearch) {
              appendLedger({ glyph: "✓", body: `Found ${data.count} hits for <em>${escapeHtml(data.input)}</em>`, meta: `via ${escapeHtml(data.transport || "?")}` });
            } else {
              appendLedger({ glyph: "✓", body: `Read <a href="${escapeHtml(data.input)}" target="_blank" rel="noopener">${escapeHtml(shortUrl(data.input))}</a>`, meta: `${(data.chars || 0).toLocaleString()} chars · ${escapeHtml(data.transport || "?")}` });
            }
          } else if (data.status === "empty") {
            appendLedger({ glyph: "∅", body: `No results for <em>${escapeHtml(data.input)}</em>`, meta: `via ${escapeHtml(data.transport || "?")}`, kind: "skipped" });
          } else if (data.status === "skipped") {
            appendLedger({ glyph: "—", body: `Skipped`, meta: escapeHtml(data.reason || ""), kind: "skipped" });
          } else if (data.status === "error") {
            appendLedger({ glyph: "!", body: `Tool error · <em>${escapeHtml(data.error || "")}</em>`, kind: "error" });
          }
          return;
        }
        if (event === "report") {
          reportEl.classList.remove("empty");
          reportEl.innerHTML = `${escapeHtml(data.text || "(no report)")}<span class="signoff">— filed by deep_research_analyst, via InstaVM</span>`;
          return;
        }
        if (event === "error") {
          appendLedger({ glyph: "✕", body: escapeHtml(data.message || "error"), kind: "error" });
          setStatus(data.message || "Failed", "error");
          return;
        }
      }

      async function submit() {
        if (!queryEl.value.trim()) return;
        runBtn.disabled = true;
        clearLedger();
        reportEl.classList.add("empty");
        reportEl.textContent = "On the press…";
        setStatus("Running…");
        dotEl.classList.add("active");

        const resp = await fetch("/api/report", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ query: queryEl.value }),
        });
        if (!resp.ok || !resp.body) {
          let msg = `HTTP ${resp.status}`;
          try {
            const j = await resp.json();
            if (j && j.detail) msg = j.detail;
          } catch (_) {}
          setStatus(msg, "error");
          appendLedger({ glyph: "✕", body: escapeHtml(msg), kind: "error" });
          dotEl.classList.remove("active");
          runBtn.disabled = false;
          return;
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buf.indexOf("\\n\\n")) !== -1) {
            const chunk = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const lines = chunk.split("\\n");
            let event = "message";
            const dataLines = [];
            for (const ln of lines) {
              if (ln.startsWith("event: ")) event = ln.slice(7).trim();
              else if (ln.startsWith("data: ")) dataLines.push(ln.slice(6));
            }
            if (!dataLines.length) continue;
            let payload = dataLines.join("\\n");
            try { payload = JSON.parse(payload); } catch (_) { /* string payload */ }
            handleEvent(event, payload);
          }
        }
        runBtn.disabled = false;
        dotEl.classList.remove("active");
      }

      runBtn.addEventListener("click", submit);
      queryEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
      });
    </script>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "ok": "true",
        "runtime": "openai-agents-research",
        "model": MODEL_NAME,
        "browser": "instavm" if _get_instavm_client() is not None else "fallback-only",
        "vault_target_host": VAULT_TARGET_HOST,
        "vault_placeholder": VAULT_PLACEHOLDER,
        "preflight_ok": "true" if (_preflight_cache and _preflight_cache.ok) else "false",
    }


@app.get("/api/preflight")
async def api_preflight() -> dict[str, Any]:
    instavm_key = _validate_orchestrator_env()
    result = await asyncio.to_thread(_run_preflight, instavm_key)
    global _preflight_cache
    _preflight_cache = result
    return result.model_dump()


async def _research_stream(query: str) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    state = RequestState(queue)
    token = _request_state.set(state)

    async def _runner() -> None:
        try:
            await queue.put(_phase("research", "active"))
            await queue.put(_sse("config", {"model": MODEL_NAME, "max_turns": MAX_AGENT_TURNS}))
            agent = _build_agent()
            run_started = time.monotonic()
            result = await Runner.run(
                agent,
                f"Research prompt: {query}",
                run_config=RunConfig(workflow_name="research-desk"),
                max_turns=MAX_AGENT_TURNS,
            )
            elapsed = time.monotonic() - run_started
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
            await queue.put(_sse("error", {"message": _friendly_provider_error(exc)}))
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
        except (BaseException,):
            pass
        if state.browser_session_id:
            client = _get_instavm_client()
            if client is not None:
                try:
                    await asyncio.to_thread(client.close_browser_session, state.browser_session_id)
                except Exception:
                    logger.exception("failed to close browser session %s", state.browser_session_id)
        _request_state.reset(token)


@app.post("/api/report")
async def create_report(request: ReportRequest) -> StreamingResponse:
    if not _preflight_cache or not _preflight_cache.ok:
        raise HTTPException(
            status_code=503,
            detail=(_preflight_cache.message if _preflight_cache else "preflight not run")
            + " — open / and follow the vault setup banner.",
        )
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
