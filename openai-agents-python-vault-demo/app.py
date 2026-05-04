"""Vault Demo cookbook.

Demonstrates the inverse threat model from injection-scanner / vibe-preview:
the OpenAI key never enters this orchestrator, never enters the child sandbox,
and is never present in any environment variable inside any VM. The cookbook
relies on InstaVM's organization-scoped vault to inject the real credential
transparently at egress, so any HTTPS client (including the OpenAI SDK) can
keep using ``OPENAI_API_KEY`` like normal but the wire carries the real value.

Setup is CLI-driven; this cookbook does not call ``create_vault`` etc. itself.
See README.md for the four CLI commands the user runs once before deploy.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from agents import RunConfig, Runner
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from instavm import InstaVM
from instavm.integrations.openai_agents import (
    InstaVMSandboxClient,
    InstaVMSandboxClientOptions,
)


# The vault API surface lives in the InstaVM SDK on dev/main but isn't yet on
# PyPI as of instavm==0.21.0. Talk to /v1/vaults over HTTP directly so this
# cookbook works against the published baseline without forcing users onto a
# pre-release SDK.
INSTAVM_API_BASE = os.environ.get("INSTAVM_API_BASE", "https://api.instavm.io").rstrip("/")


def _vault_get(instavm_key: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
    url = f"{INSTAVM_API_BASE}{path}"
    # InstaVM's API gateway expects X-API-Key (not Bearer). See sandbox_client._auth_headers.
    headers = {"X-API-Key": instavm_key}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

logger = logging.getLogger("vault_demo")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")
PLACEHOLDER = os.environ.get("VAULT_DEMO_PLACEHOLDER", "OPENAI_KEY")
TARGET_HOST = os.environ.get("VAULT_DEMO_HOST", "api.openai.com")
SANDBOX_MEMORY_MB = int(os.environ.get("VAULT_SANDBOX_MEMORY_MB", "1024"))
SANDBOX_TIMEOUT = int(os.environ.get("VAULT_SANDBOX_TIMEOUT_S", "600"))


def _looks_like_real_openai_key(value: str) -> bool:
    """Heuristic: real OpenAI keys start with sk- and are >= 20 chars.

    The cookbook actively refuses to run if a real key is present in the
    orchestrator's environment, because that defeats the demo. Users wanting
    the standard "key in orchestrator" pattern should deploy vibe-preview /
    injection-scanner instead.
    """
    v = (value or "").strip()
    return v.startswith("sk-") and len(v) >= 20


def _validate_orchestrator_env() -> str:
    """Verify the orchestrator is in vault-mode and return INSTAVM_API_KEY."""
    instavm_key = (os.environ.get("INSTAVM_API_KEY") or "").strip()
    if not instavm_key or instavm_key.lower() in {"changeme", "placeholder", "test"}:
        raise RuntimeError(
            "INSTAVM_API_KEY is required. The orchestrator uses it to spawn "
            "child sandboxes and to query vault request logs."
        )

    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if _looks_like_real_openai_key(openai_key):
        raise RuntimeError(
            "OPENAI_API_KEY appears to be a real OpenAI key (starts with 'sk-'). "
            "This cookbook demonstrates vault-based credential injection: the "
            "real key should live ONLY in the InstaVM vault, not in this "
            "orchestrator's environment. Unset OPENAI_API_KEY or set it to a "
            "placeholder name like 'OPENAI_KEY' that matches a credential "
            "bound in your vault to api.openai.com."
        )

    # Force the placeholder so the OpenAI SDK doesn't 401 before the vault
    # sees the request. The MITM proxy substitutes the real value on the wire.
    os.environ["OPENAI_API_KEY"] = PLACEHOLDER
    return instavm_key


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


def _vault_client(instavm_key: str) -> InstaVM:
    # auto_start_session=False means we DON'T spawn a sandbox — this client
    # is only used for vault management/log queries.
    return InstaVM(api_key=instavm_key, auto_start_session=False)


def _list_vaults(instavm_key: str) -> list[dict[str, Any]]:
    payload = _vault_get(instavm_key, "/v1/vaults")
    return payload.get("vaults", []) if isinstance(payload, dict) else []


def _list_vault_services(instavm_key: str, vault_id: str) -> list[dict[str, Any]]:
    payload = _vault_get(instavm_key, f"/v1/vaults/{vault_id}/services")
    return payload.get("services", []) if isinstance(payload, dict) else []


def _list_vault_request_logs(instavm_key: str, vault_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    payload = _vault_get(
        instavm_key, f"/v1/vaults/{vault_id}/request-logs", params={"limit": limit}
    )
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("logs") or payload.get("entries") or []
    return []


def _run_preflight(instavm_key: str) -> VaultPreflight:
    """Look for an org vault that has a service binding to TARGET_HOST.

    Returns the first vault that satisfies the binding; surfaces a friendly
    error otherwise so the user can fix it via the CLI without redeploying.
    """
    cli_hint = [
        f'VAULT_ID=$(instavm vault create cookbook-demo -j | python3 -c "import sys,json; print(json.load(sys.stdin)[\\"id\\"])")',
        f'instavm vault secret set "$VAULT_ID" {PLACEHOLDER}',
        f'instavm vault service add "$VAULT_ID" --host {TARGET_HOST} --auth-type bearer --credential {PLACEHOLDER}',
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
                "Your organization has no vaults yet. Run the four CLI "
                "commands shown to create one bound to api.openai.com."
            ),
            cli_hint=cli_hint,
        )

    # Find the first vault with a binding to TARGET_HOST.
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
            if host != TARGET_HOST:
                continue
            auth_cfg = svc.get("auth_config") or {}
            credential = (
                auth_cfg.get("token")
                or auth_cfg.get("key")
                or auth_cfg.get("credential")
                or PLACEHOLDER
            )
            return VaultPreflight(
                ok=True,
                vault_id=vault_id,
                vault_name=str(vault.get("name") or vault_id),
                credential_name=str(credential),
                message=(
                    f"Vault '{vault.get('name') or vault_id}' has a binding to "
                    f"{TARGET_HOST}. Real credential will be substituted on the wire."
                ),
            )

    return VaultPreflight(
        ok=False,
        message=(
            f"None of your {len(vaults)} vault(s) has a service binding to "
            f"{TARGET_HOST}. Run the CLI commands shown to add one."
        ),
        cli_hint=cli_hint,
    )


# ---------------------------------------------------------------------------
# FastAPI app + lifespan
# ---------------------------------------------------------------------------


# Track active sandboxes for cleanup on shutdown.
_active_sandboxes: list[tuple[InstaVMSandboxClient, Any]] = []
_active_lock = asyncio.Lock()
_preflight_cache: VaultPreflight | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _preflight_cache
    instavm_key = _validate_orchestrator_env()
    try:
        _preflight_cache = await asyncio.to_thread(_run_preflight, instavm_key)
    except Exception as exc:
        logger.exception("preflight failed")
        _preflight_cache = VaultPreflight(
            ok=False,
            message=f"Preflight raised: {exc!s}",
        )
    if _preflight_cache.ok:
        logger.info(
            "preflight passed: vault=%s credential=%s",
            _preflight_cache.vault_name,
            _preflight_cache.credential_name,
        )
    else:
        logger.warning("preflight failed: %s", _preflight_cache.message)

    yield

    async with _active_lock:
        items = list(_active_sandboxes)
        _active_sandboxes.clear()
    for client, sandbox in items:
        try:
            await client.delete(sandbox)
        except Exception:
            logger.exception("failed to clean up sandbox on shutdown")


app = FastAPI(title="Vault Demo", lifespan=_lifespan)


class AskRequest(BaseModel):
    prompt: str


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


HTML = r"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Vault Demo &middot; OpenAI Agents SDK on InstaVM</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <style>
      :root {
        color-scheme: dark;
        --bg: #08090a;
        --surface: #0f1011;
        --surface-2: #15171a;
        --surface-3: #1a1d21;
        --border: #1f2225;
        --border-strong: #2a2d32;
        --ink: #e8e9ea;
        --ink-2: #c8c9cb;
        --muted: #8a8d92;
        --muted-2: #5b5e63;
        --accent: #4ade80;
        --accent-bg: rgba(74,222,128,0.10);
        --accent-border: rgba(74,222,128,0.28);
        --info: #60a5fa;
        --warn: #fbbf24;
        --danger: #f87171;
        --radius-sm: 6px;
        --radius: 8px;
      }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      html, body { height: 100%; }
      body {
        font-family: "Inter", -apple-system, system-ui, sans-serif;
        font-size: 14px; line-height: 1.5;
        color: var(--ink); background: var(--bg);
        -webkit-font-smoothing: antialiased;
      }
      main { max-width: 1320px; margin: 0 auto; padding: 32px 24px 64px; }
      header { margin-bottom: 28px; }
      .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; font-size: 13px; color: var(--muted); }
      .brand .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px var(--accent-bg); }
      h1 { font-size: 28px; font-weight: 600; letter-spacing: -0.025em; margin-bottom: 8px; }
      .subtitle { color: var(--muted); max-width: 780px; }
      .subtitle b { color: var(--ink-2); font-weight: 500; }
      .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 14px; }
      .chip {
        padding: 3px 9px; border-radius: var(--radius-sm); font-size: 12px;
        font-weight: 450; color: var(--muted);
        background: var(--surface-2); border: 1px solid var(--border);
      }
      .grid {
        display: grid; gap: 16px; margin-top: 14px;
        grid-template-columns: minmax(0, 1fr);
      }
      @media (min-width: 1040px) {
        .grid { grid-template-columns: 380px minmax(0, 1fr); }
      }
      .card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius);
      }
      .card.input-card { padding: 18px; }
      .card.output-card { padding: 0; overflow: hidden; display: flex; flex-direction: column; min-height: 540px; }
      .panel-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 14px 18px; border-bottom: 1px solid var(--border);
        font-size: 13px; font-weight: 500; color: var(--ink-2);
      }
      .panel-header .meta { color: var(--muted); font-size: 12px; font-weight: 400; }
      h2 { font-size: 13px; font-weight: 500; color: var(--ink-2); margin-bottom: 12px; }
      label { display: block; font-size: 12px; font-weight: 450; color: var(--muted); margin-bottom: 6px; }
      textarea {
        width: 100%; min-height: 120px; padding: 10px 12px;
        font: inherit; font-size: 13.5px; line-height: 1.5; color: var(--ink);
        background: var(--surface-2); border: 1px solid var(--border);
        border-radius: var(--radius-sm); resize: vertical; outline: none;
      }
      textarea:focus { border-color: var(--accent-border); box-shadow: 0 0 0 3px var(--accent-bg); }
      .examples { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
      .example {
        padding: 7px 10px; background: transparent;
        border: 1px solid var(--border); border-radius: var(--radius-sm);
        font-size: 13px; color: var(--muted); cursor: pointer;
        text-align: left; font: inherit;
      }
      .example:hover { color: var(--ink); border-color: var(--border-strong); background: var(--surface-2); }
      .actions { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
      .btn {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 8px 14px; border: 1px solid var(--accent-border);
        border-radius: var(--radius-sm); font: inherit; font-size: 13px; font-weight: 500;
        color: var(--ink); background: var(--accent-bg); cursor: pointer;
      }
      .btn:hover:not(:disabled) { background: rgba(74,222,128,0.18); border-color: rgba(74,222,128,0.45); }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .kbd { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11px; color: var(--muted); padding: 1px 5px; border: 1px solid var(--border); border-radius: 4px; }

      .preflight {
        margin: 16px 18px 0; padding: 12px 14px;
        border-radius: var(--radius-sm);
        background: var(--surface-2); border: 1px solid var(--border);
        font-size: 13px; line-height: 1.55;
      }
      .preflight.ok { border-color: var(--accent-border); background: var(--accent-bg); }
      .preflight.fail { border-color: rgba(251,191,36,0.35); background: rgba(251,191,36,0.07); }
      .preflight .label { font-size: 11px; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }
      .preflight .label .pill { display: inline-block; padding: 1px 6px; border-radius: 3px; font-weight: 600; }
      .preflight.ok .pill { color: var(--accent); background: rgba(74,222,128,0.12); }
      .preflight.fail .pill { color: var(--warn); background: rgba(251,191,36,0.15); }
      .preflight pre {
        margin-top: 8px; padding: 8px 10px; background: var(--bg); border: 1px solid var(--border);
        border-radius: 4px; font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 11.5px; color: var(--ink-2); white-space: pre-wrap; overflow-x: auto;
      }

      .phases { padding: 14px 18px; border-bottom: 1px solid var(--border); }
      .phases-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
      .phase {
        display: inline-flex; align-items: center; gap: 7px;
        padding: 5px 10px; border-radius: var(--radius-sm);
        font-size: 12.5px; font-weight: 450; color: var(--muted-2);
        background: transparent; border: 1px solid var(--border);
      }
      .phase[data-status="active"] { color: var(--ink); background: var(--accent-bg); border-color: var(--accent-border); }
      .phase[data-status="done"]   { color: var(--ink-2); background: var(--accent-bg); border-color: var(--accent-border); }
      .phase[data-status="error"]  { color: var(--danger); border-color: rgba(248,113,113,0.4); background: rgba(248,113,113,0.08); }
      .phase .ind {
        width: 12px; height: 12px; flex-shrink: 0; display: inline-block;
        border-radius: 50%; border: 1.5px solid currentColor; opacity: 0.55;
        position: relative;
      }
      .phase[data-status="active"] .ind { border-color: var(--accent); opacity: 1; }
      .phase[data-status="active"] .ind::after {
        content: ""; position: absolute; inset: -1.5px; border-radius: 50%;
        border: 1.5px solid transparent; border-top-color: var(--accent);
        animation: spin 0.7s linear infinite;
      }
      .phase[data-status="done"] .ind {
        background: var(--accent); border-color: var(--accent); opacity: 1;
      }
      .phase[data-status="done"] .ind::after {
        content: ""; position: absolute; left: 3px; top: 0px; width: 4px; height: 7px;
        border: solid #08090a; border-width: 0 1.5px 1.5px 0; transform: rotate(45deg);
      }
      .phase-arrow { color: var(--muted-2); font-size: 11px; }
      @keyframes spin { to { transform: rotate(360deg); } }

      .answer-pane { padding: 16px 18px; flex: 1 1 auto; overflow-y: auto; }
      .answer-empty { padding: 36px 18px; text-align: center; color: var(--muted-2); font-size: 13px; }
      .answer-text {
        font-size: 14.5px; line-height: 1.6; color: var(--ink);
        white-space: pre-wrap; word-break: break-word;
      }
      .answer-meta { color: var(--muted); font-size: 11.5px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); display: flex; gap: 14px; flex-wrap: wrap; }

      .wirelog {
        border-top: 1px solid var(--border); padding: 14px 18px;
        background: var(--surface-2);
      }
      .wirelog h3 {
        font-size: 11.5px; font-weight: 500; color: var(--muted);
        letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 8px;
      }
      .wirelog table {
        width: 100%; border-collapse: collapse;
        font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 11.5px; color: var(--ink-2);
      }
      .wirelog th, .wirelog td {
        text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border);
      }
      .wirelog th { color: var(--muted); font-weight: 500; }
      .wirelog tr:last-child td { border-bottom: 0; }
      .wirelog .stat-2 { color: var(--accent); }
      .wirelog .stat-4, .wirelog .stat-5 { color: var(--danger); }
      .wirelog-empty { color: var(--muted-2); font-style: italic; padding: 6px 0; }

      .error-banner {
        margin: 14px 18px; padding: 10px 14px;
        background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.28);
        border-radius: var(--radius-sm); color: var(--danger); font-size: 13px;
        font-family: "JetBrains Mono", ui-monospace, monospace;
      }
      .sec-note {
        margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border);
        font-size: 12px; line-height: 1.55; color: var(--muted);
      }
      .sec-note b { color: var(--ink-2); font-weight: 500; }
      code { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 12px; background: var(--surface-2); padding: 1px 5px; border-radius: 3px; color: var(--ink-2); }
    </style>
  </head>
  <body>
    <main>
      <header>
        <div class="brand"><span class="dot"></span> Vault Demo &middot; OpenAI Agents SDK on InstaVM</div>
        <h1>Call OpenAI without ever holding the key.</h1>
        <p class="subtitle">This orchestrator's <code>OPENAI_API_KEY</code> is literally the string <code>__PLACEHOLDER__</code>. The real key lives only in your InstaVM <b>Vault</b>, bound to <code>__HOST__</code>. The platform's egress proxy substitutes it on the wire for every HTTPS request &mdash; both for the model call here and for any tool calls inside the child sandbox.</p>
        <div class="chips">
          <span class="chip">No real key in orchestrator</span>
          <span class="chip">No real key in sandbox</span>
          <span class="chip">Wire substitution at egress</span>
          <span class="chip">CLI-driven setup, one credential</span>
        </div>
      </header>
      <div id="preflight-host"></div>
      <div class="grid">
        <section class="card input-card">
          <h2>Ask the model</h2>
          <label for="prompt">Prompt</label>
          <textarea id="prompt" placeholder="Explain in one sentence what an InstaVM vault is.">Explain in one sentence what an InstaVM vault is.</textarea>
          <div class="examples">
            <button class="example" data-prompt="Why does deny-by-default egress make prompt injection harder to exploit?">Egress security question</button>
            <button class="example" data-prompt="Write a haiku about credential injection at TLS write time.">Haiku</button>
            <button class="example" data-prompt="Compare a Firecracker microVM to a Docker container in three bullet points.">Firecracker vs Docker</button>
          </div>
          <div class="actions">
            <button class="btn" id="ask">Ask</button>
            <span class="kbd">&#x2318; Enter</span>
          </div>
          <div class="sec-note">
            <b>What proves the substitution worked?</b> The wire log under the answer is queried from the InstaVM control plane <em>after</em> each request and shows that <code>__HOST__</code> was hit by your vault &mdash; with which credential, when, and the upstream HTTP status. If the substitution failed, you would see <code>401</code> back from OpenAI here.
          </div>
        </section>
        <section class="card output-card">
          <div class="panel-header">
            <span>Agent output</span>
            <span class="meta" id="output-meta"></span>
          </div>
          <div class="phases" id="phases-host" style="display:none;">
            <div class="phases-row" id="phases-row"></div>
          </div>
          <div class="answer-pane" id="answer-pane">
            <div class="answer-empty">Click <b>Ask</b> to send the prompt through the vault.</div>
          </div>
          <div id="error-host"></div>
          <div class="wirelog" id="wirelog-host" style="display:none;">
            <h3>Vault wire log (last 5 requests)</h3>
            <div id="wirelog-body"></div>
          </div>
        </section>
      </div>
    </main>
    <script>
      const promptEl = document.getElementById("prompt");
      const askBtn = document.getElementById("ask");
      const phasesHost = document.getElementById("phases-host");
      const phasesRow = document.getElementById("phases-row");
      const answerPane = document.getElementById("answer-pane");
      const errorHost = document.getElementById("error-host");
      const outputMeta = document.getElementById("output-meta");
      const preflightHost = document.getElementById("preflight-host");
      const wirelogHost = document.getElementById("wirelog-host");
      const wirelogBody = document.getElementById("wirelog-body");

      const phaseEls = new Map();
      let runStart = 0;

      document.querySelectorAll(".example").forEach(el => {
        el.addEventListener("click", () => { promptEl.value = el.dataset.prompt; promptEl.focus(); });
      });
      promptEl.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !askBtn.disabled) ask();
      });

      async function loadPreflight() {
        try {
          const r = await fetch("/api/preflight");
          const data = await r.json();
          renderPreflight(data);
        } catch (e) {
          renderPreflight({ ok: false, message: "Could not reach /api/preflight." });
        }
      }

      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
      }

      function renderPreflight(p) {
        const klass = p.ok ? "ok" : "fail";
        const label = p.ok ? "Vault preflight" : "Vault not configured";
        const pill = p.ok ? "PASS" : "FIX";
        const cliBlock = (!p.ok && Array.isArray(p.cli_hint))
          ? `<pre>${p.cli_hint.map(escapeHtml).join("\n")}</pre>`
          : "";
        let extras = "";
        if (p.ok) {
          extras = `<div style="margin-top:6px;color:var(--muted);font-size:12px;">vault: <code>${escapeHtml(p.vault_name||"")}</code> &middot; credential: <code>${escapeHtml(p.credential_name||"")}</code></div>`;
        }
        preflightHost.innerHTML = `
          <div class="preflight ${klass}">
            <div class="label">${label} <span class="pill">${pill}</span></div>
            <div>${escapeHtml(p.message || "")}</div>
            ${extras}
            ${cliBlock}
          </div>`;
        if (!p.ok) askBtn.disabled = true;
      }

      function setPhases(phases) {
        phasesRow.innerHTML = ""; phaseEls.clear();
        phases.forEach((p, i) => {
          if (i > 0) {
            const arrow = document.createElement("span");
            arrow.className = "phase-arrow"; arrow.textContent = "›";
            phasesRow.appendChild(arrow);
          }
          const el = document.createElement("span");
          el.className = "phase"; el.dataset.status = "pending";
          el.dataset.id = p.id;
          el.innerHTML = `<span class="ind"></span><span class="lbl"></span>`;
          el.querySelector(".lbl").textContent = p.label;
          phasesRow.appendChild(el);
          phaseEls.set(p.id, el);
        });
        phasesHost.style.display = "block";
      }

      function updatePhase(id, status) {
        const el = phaseEls.get(id);
        if (el) el.dataset.status = status;
      }

      function showError(msg) {
        errorHost.innerHTML = `<div class="error-banner"></div>`;
        errorHost.firstChild.textContent = msg;
      }

      function resetUI() {
        answerPane.innerHTML = "";
        errorHost.innerHTML = "";
        phasesRow.innerHTML = "";
        phasesHost.style.display = "none";
        phaseEls.clear();
        outputMeta.textContent = "";
        wirelogHost.style.display = "none";
        wirelogBody.innerHTML = "";
      }

      function renderAnswer(text) {
        answerPane.innerHTML = `<div class="answer-text"></div><div class="answer-meta"><span>Model: <code>${escapeHtml(MODEL)}</code></span><span>Wire host: <code>${escapeHtml(HOST)}</code></span></div>`;
        answerPane.querySelector(".answer-text").textContent = text;
      }

      function renderWireLog(entries) {
        wirelogHost.style.display = "block";
        if (!entries || entries.length === 0) {
          wirelogBody.innerHTML = `<div class="wirelog-empty">No wire activity captured. Either the vault has no logs retention, or the request did not hit the proxy.</div>`;
          return;
        }
        const rows = entries.map(e => {
          const ts = e.timestamp || e.created_at || "";
          const host = e.host || e.upstream_host || "";
          const status = e.status_code || e.status || "";
          const cred = e.credential_name || e.credential || "";
          const stCls = (typeof status === "number" || /^\d/.test(String(status))) ? `stat-${String(status).charAt(0)}` : "";
          return `<tr><td>${escapeHtml(ts)}</td><td>${escapeHtml(host)}</td><td>${escapeHtml(cred)}</td><td class="${stCls}">${escapeHtml(String(status))}</td></tr>`;
        }).join("");
        wirelogBody.innerHTML = `<table><thead><tr><th>Time</th><th>Host</th><th>Credential</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
      }

      let MODEL = "";
      let HOST = "";

      async function ask() {
        if (!promptEl.value.trim()) { promptEl.focus(); return; }
        askBtn.disabled = true;
        resetUI();
        runStart = Date.now();

        let response;
        try {
          response = await fetch("/api/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: promptEl.value }),
          });
        } catch (e) {
          showError("Connection failed. Is the orchestrator reachable?");
          askBtn.disabled = false;
          return;
        }
        if (!response.ok) {
          let msg = "Request failed.";
          try { msg = (await response.json()).detail || msg; } catch {}
          showError(msg);
          askBtn.disabled = false;
          return;
        }

        const reader = response.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let idx;
          while ((idx = buf.indexOf("\n\n")) !== -1) {
            const frame = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const lines = frame.split("\n");
            let event = "message"; const data = [];
            for (const line of lines) {
              if (line.startsWith("event:")) event = line.slice(6).trim();
              else if (line.startsWith("data:")) data.push(line.slice(5).trim());
            }
            handleEvent(event, data.join("\n"));
          }
        }
        askBtn.disabled = false;
        const sec = ((Date.now() - runStart) / 1000).toFixed(1);
        outputMeta.textContent = `${sec}s`;
      }

      function handleEvent(event, raw) {
        let data;
        try { data = JSON.parse(raw); } catch { data = { text: raw }; }
        if (event === "config") {
          MODEL = data.model || ""; HOST = data.host || "";
        } else if (event === "phases") {
          setPhases(data.phases || []);
        } else if (event === "phase") {
          updatePhase(data.id, data.status);
        } else if (event === "answer") {
          renderAnswer(data.text || "");
        } else if (event === "wirelog") {
          renderWireLog(data.entries || []);
        } else if (event === "error") {
          showError(data.message || "Run failed.");
          phaseEls.forEach((el) => {
            if (el.dataset.status === "active") el.dataset.status = "error";
          });
        }
      }

      askBtn.addEventListener("click", ask);
      loadPreflight();
    </script>
  </body>
</html>
"""


def _render_html() -> str:
    return HTML.replace("__PLACEHOLDER__", PLACEHOLDER).replace("__HOST__", TARGET_HOST)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _render_html()


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "ok": "true",
        "runtime": "openai-agents-vault-demo",
        "model": MODEL_NAME,
        "host": TARGET_HOST,
        "preflight_ok": "true" if (_preflight_cache and _preflight_cache.ok) else "false",
    }


@app.get("/api/preflight")
async def preflight_endpoint() -> VaultPreflight:
    """Return the cached preflight result; re-run on each call to keep it fresh."""
    instavm_key = _validate_orchestrator_env()
    result = await asyncio.to_thread(_run_preflight, instavm_key)
    global _preflight_cache
    _preflight_cache = result
    return result


def _sse(event: str, data: dict[str, Any] | str) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _phase(phase_id: str, status: str) -> bytes:
    return _sse("phase", {"id": phase_id, "status": status})


HEARTBEAT_INTERVAL_S = float(os.environ.get("VAULT_SSE_HEARTBEAT_S", "8"))


async def _with_heartbeats(
    inner: AsyncIterator[bytes], interval: float = HEARTBEAT_INTERVAL_S
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
    done = asyncio.Event()

    async def producer() -> None:
        try:
            async for chunk in inner:
                await queue.put(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("stream producer failed")
            try:
                await queue.put(_sse("error", {"message": f"stream failed: {exc!s}"[:600]}))
            except Exception:
                pass
        finally:
            done.set()
            await queue.put(None)

    task = asyncio.create_task(producer())
    yield b": " + (b" " * 2048) + b"\n\n"
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                if done.is_set():
                    break
                yield b": keepalive\n\n"
                continue
            if chunk is None:
                break
            yield chunk
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------


VAULT_DEMO_INSTRUCTIONS = (
    "You are a concise assistant. Answer the user's question directly in plain "
    "prose, 1-3 short paragraphs. No code blocks unless explicitly asked. No "
    "bullet lists unless the question is naturally a list. Do not narrate that "
    "you are using a sandbox. Just answer."
)


async def _ask_stream(prompt: str) -> AsyncIterator[bytes]:
    yield _sse("config", {"model": MODEL_NAME, "host": TARGET_HOST})
    yield _sse(
        "phases",
        {
            "phases": [
                {"id": "provision", "label": "Provision sandbox"},
                {"id": "boot", "label": "Boot microVM"},
                {"id": "respond", "label": "Call OpenAI via vault"},
                {"id": "audit", "label": "Pull wire log"},
            ]
        },
    )
    yield _phase("provision", "active")

    instavm_key = _validate_orchestrator_env()
    if not _preflight_cache or not _preflight_cache.ok:
        yield _sse(
            "error",
            {
                "message": (
                    "Vault preflight has not passed yet. Refresh the page or run "
                    "the CLI commands shown at the top of the UI."
                )
            },
        )
        yield _phase("provision", "error")
        return

    client = InstaVMSandboxClient(api_key=instavm_key)
    sandbox = None
    try:
        sandbox = await client.create(
            manifest=Manifest(entries={}),
            options=InstaVMSandboxClientOptions(
                memory_mb=SANDBOX_MEMORY_MB,
                cpu_count=2,
                timeout=SANDBOX_TIMEOUT,
                env={"OPENAI_API_KEY": PLACEHOLDER},
                allow_internet_access=True,
                allow_https=True,
                allow_http=False,
                allow_package_managers=True,
                allowed_domains=(TARGET_HOST,),
            ),
        )
        async with _active_lock:
            _active_sandboxes.append((client, sandbox))

        yield _phase("provision", "done")
        yield _phase("boot", "active")

        await sandbox.start()

        yield _phase("boot", "done")
        yield _phase("respond", "active")

        agent = SandboxAgent(
            name="Vault Demo",
            model=MODEL_NAME,
            instructions=VAULT_DEMO_INSTRUCTIONS,
            default_manifest=Manifest(entries={}),
        )
        # The Agents SDK runs the model from this orchestrator process. The
        # OpenAI SDK reads OPENAI_API_KEY (which we forced to the placeholder)
        # and the vault MITM substitutes the real value at TLS write time.
        result = await Runner.run(
            agent,
            prompt,
            run_config=RunConfig(
                sandbox=SandboxRunConfig(session=sandbox),
                workflow_name="vault-demo",
            ),
            max_turns=2,
        )
        answer = (result.final_output or "").strip() if result else ""
        yield _phase("respond", "done")
        yield _sse("answer", {"text": answer or "(empty answer)"})

        yield _phase("audit", "active")
        try:
            wire = await asyncio.to_thread(
                _list_vault_request_logs,
                instavm_key,
                _preflight_cache.vault_id,
                limit=5,
            )
        except Exception as exc:
            logger.warning("could not fetch wire log: %s", exc)
            wire = []
        yield _sse("wirelog", {"entries": wire or []})
        yield _phase("audit", "done")
    except Exception as exc:
        logger.exception("ask failed")
        yield _sse("error", {"message": str(exc)[:600]})
    finally:
        if sandbox is not None:
            try:
                async with _active_lock:
                    for i, (c, s) in enumerate(_active_sandboxes):
                        if s is sandbox:
                            _active_sandboxes.pop(i)
                            break
                await client.delete(sandbox)
            except Exception:
                logger.exception("failed to clean up sandbox after run")
        yield _sse("done", {})


@app.post("/api/ask")
async def ask(req: AskRequest) -> StreamingResponse:
    _validate_orchestrator_env()
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")
    if len(prompt) > 4000:
        raise HTTPException(status_code=413, detail="Prompt exceeds 4000 characters.")
    return StreamingResponse(
        _with_heartbeats(_ask_stream(prompt)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
