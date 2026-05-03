from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from agents import RunConfig, Runner
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.entries import File
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from openai.types.responses import ResponseTextDeltaEvent
from pydantic import BaseModel

from instavm.integrations.openai_agents import (
    InstaVMSandboxClient,
    InstaVMSandboxClientOptions,
)

logger = logging.getLogger("vibe_preview")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-5.4-nano")
PREVIEW_PORT = 8080
PREVIEW_TTL_SECONDS = int(os.environ.get("VIBE_PREVIEW_TTL_SECONDS", "900"))
SANDBOX_MEMORY_MB = int(os.environ.get("VIBE_SANDBOX_MEMORY_MB", "2048"))
SANDBOX_TIMEOUT = max(PREVIEW_TTL_SECONDS, 600)


def looks_like_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    return any(
        marker in normalized
        for marker in (
            "dummy",
            "test",
            "placeholder",
            "your_key",
            "your-api-key",
            "changeme",
            "example",
        )
    )


BUILDER_INSTRUCTIONS = (
    "You are a senior front-end engineer with a Linux sandbox. Your job is to "
    "build a small web app the user describes and serve it on port 8080.\n\n"
    "Hard requirements:\n"
    "- Workspace root is /workspace. Put all sources under /workspace/app/.\n"
    "- Use ONLY the Python standard library (http.server, html, json, sqlite3, "
    "etc.) unless the task truly needs more. The sandbox has no internet egress "
    "for arbitrary domains; only PyPI/apt mirrors are reachable.\n"
    "- Make the UI visually polished: real CSS, modern fonts, responsive layout, "
    "no Bootstrap/CDNs (no internet). Inline assets.\n"
    "- Start the server in the background so this shell session can return:\n"
    "    nohup python3 -m http.server 8080 --directory /workspace/app/public >/tmp/srv.log 2>&1 &\n"
    "  (use a custom Python script for dynamic apps; bind to 0.0.0.0:8080.)\n"
    "- After starting, verify with `sleep 1 && curl -fsS http://127.0.0.1:8080/` "
    "and ensure HTTP 200.\n"
    "- If it works, your final message must be a short summary in JSON:\n"
    '    {"status":"ready","entrypoint":"<file>","stack":"<short>"}\n'
    "  No prose, no fences, no code blocks in the final message.\n"
    "- If you cannot make it serve, return:\n"
    '    {"status":"error","reason":"<short cause>"}\n'
)


class BuildRequest(BaseModel):
    prompt: str


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Vibe Preview</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
    <style>
      :root {
        color-scheme: dark;
        --bg: #0b0a18;
        --surface: rgba(28, 22, 50, 0.55);
        --glass: rgba(36, 28, 64, 0.42);
        --ink: #ece8f5;
        --muted: #948cb0;
        --accent: #a78bfa;
        --accent-2: #f472b6;
        --accent-soft: rgba(167, 139, 250, 0.12);
        --accent-glow: rgba(167, 139, 250, 0.28);
        --border: rgba(167, 139, 250, 0.18);
        --good: #34d399;
        --radius: 16px;
      }
      * { box-sizing: border-box; margin: 0; }
      body { font-family: "Inter", system-ui, sans-serif; color: var(--ink); background: var(--bg); min-height: 100vh; }
      body::before {
        content: "";
        position: fixed; inset: 0; z-index: -1;
        background:
          radial-gradient(ellipse 70% 50% at 20% 10%, rgba(167,139,250,0.13), transparent),
          radial-gradient(ellipse 60% 40% at 80% 85%, rgba(244,114,182,0.10), transparent),
          radial-gradient(ellipse 50% 50% at 50% 50%, rgba(11,10,24,0.18), transparent);
      }
      main { max-width: 1280px; margin: 0 auto; padding: 2.2rem 1.25rem 4rem; }
      header { margin-bottom: 1.6rem; }
      h1 {
        font-family: "Space Grotesk", sans-serif;
        font-size: clamp(2rem, 5vw, 2.6rem);
        font-weight: 700;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #ece8f5 30%, var(--accent), var(--accent-2));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      .subtitle { color: var(--muted); line-height: 1.55; margin-top: 0.5rem; font-size: 0.92rem; max-width: 760px; }
      .chips { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.95rem 0 0; }
      .chip { border-radius: 999px; padding: 0.25rem 0.65rem; background: var(--accent-soft); color: var(--accent); font-size: 0.78rem; font-weight: 500; border: 1px solid var(--border); }
      .grid { display: grid; gap: 1rem; }
      @media (min-width: 980px) { .grid { grid-template-columns: minmax(0, 0.85fr) minmax(0, 1.15fr); } }
      .glass { background: var(--glass); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.15rem 1.25rem; backdrop-filter: blur(18px) saturate(1.4); -webkit-backdrop-filter: blur(18px) saturate(1.4); box-shadow: 0 8px 32px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.04); }
      h2 { font-family: "Space Grotesk", sans-serif; font-size: 1rem; font-weight: 600; margin-bottom: 0.7rem; color: var(--accent); letter-spacing: -0.01em; }
      label { font-weight: 500; font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
      textarea { width: 100%; min-height: 180px; margin-top: 0.5rem; border: 1px solid var(--border); border-radius: 12px; padding: 0.85rem 1rem; font: inherit; font-size: 0.92rem; resize: vertical; background: rgba(0,0,0,0.3); color: var(--ink); transition: border-color 0.25s, box-shadow 0.25s; outline: none; }
      textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
      .examples { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.7rem; }
      .example { padding: 0.5rem 0.7rem; background: rgba(0,0,0,0.2); border: 1px solid var(--border); border-radius: 10px; font-size: 0.82rem; color: var(--muted); cursor: pointer; transition: all 0.2s; }
      .example:hover { color: var(--ink); border-color: var(--accent); background: var(--accent-soft); }
      button { margin-top: 0.95rem; border: 0; border-radius: 999px; padding: 0.75rem 1.5rem; font: inherit; font-weight: 600; font-size: 0.9rem; cursor: pointer; color: #1a0a2e; background: linear-gradient(135deg, var(--accent), var(--accent-2)); box-shadow: 0 2px 12px rgba(167,139,250,0.3); transition: transform 0.2s cubic-bezier(.4,0,.2,1), box-shadow 0.2s; }
      button:hover:not(:disabled) { transform: translateY(-1px) scale(1.02); box-shadow: 0 4px 20px rgba(167,139,250,0.4); }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
      .timeline { display: flex; flex-direction: column; gap: 0.55rem; max-height: 500px; overflow-y: auto; padding-right: 0.25rem; }
      .timeline::-webkit-scrollbar { width: 6px; }
      .timeline::-webkit-scrollbar-thumb { background: rgba(167,139,250,0.3); border-radius: 3px; }
      .step { border-left: 2px solid rgba(167,139,250,0.4); padding: 0.4rem 0.6rem; background: rgba(0,0,0,0.18); border-radius: 0 8px 8px 0; font-size: 0.82rem; }
      .step .label { color: var(--accent); font-weight: 500; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.05em; }
      .step .body { font-family: "SF Mono", "Fira Code", monospace; color: var(--ink); white-space: pre-wrap; word-break: break-word; margin-top: 0.2rem; line-height: 1.45; max-height: 160px; overflow-y: auto; }
      .preview { margin-top: 1rem; padding: 0.85rem 0.95rem; border-radius: var(--radius); background: rgba(0,0,0,0.3); border: 1px solid var(--border); animation: in 0.4s ease; }
      @keyframes in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
      .preview .meta { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.55rem; font-size: 0.84rem; }
      .badge { display: inline-block; padding: 0.18rem 0.55rem; border-radius: 999px; font-weight: 600; font-size: 0.74rem; letter-spacing: 0.04em; background: rgba(52,211,153,0.15); color: var(--good); border: 1px solid rgba(52,211,153,0.3); }
      .preview a { color: var(--accent-2); text-decoration: underline; word-break: break-all; }
      .preview .ttl { margin-left: auto; color: var(--muted); font-size: 0.78rem; }
      .preview iframe { width: 100%; height: 520px; border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; background: white; }
      .status-row { display: flex; align-items: center; gap: 0.5rem; min-height: 1.2rem; margin-top: 0.7rem; font-size: 0.84rem; }
      #status { font-weight: 600; color: var(--accent); }
      .pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); display: none; animation: pulse 1.4s ease-in-out infinite; }
      .pulse-dot.active { display: block; }
      @keyframes pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.75); } }
      .sec-note { margin-top: 0.85rem; font-size: 0.78rem; color: var(--muted); padding-top: 0.7rem; border-top: 1px solid rgba(255,255,255,0.06); line-height: 1.5; }
      .sec-note b { color: var(--ink); }
      .empty { color: var(--muted); font-size: 0.85rem; padding: 0.6rem 0; }
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>Vibe Preview</h1>
        <p class="subtitle">Describe a small web app. The agent scaffolds it inside a fresh <b>InstaVM</b> microVM, serves it on port 8080, and we hand you a public TLS preview URL backed by an InstaVM share. The model runs here; the sandbox runs the code.</p>
        <div class="chips">
          <span class="chip">OpenAI Agents SDK</span>
          <span class="chip">InstaVM sandbox provider</span>
          <span class="chip">Live TLS share</span>
          <span class="chip">No keys in sandbox</span>
        </div>
      </header>
      <div class="grid">
        <section class="glass">
          <h2>Describe your app</h2>
          <label for="prompt">Prompt</label>
          <textarea id="prompt" placeholder="A retro-styled tip calculator with split-by-N controls, dark mode, and a sticky total card.">A retro-styled tip calculator with split-by-N controls, dark mode, and a sticky total card. Pure HTML/CSS/JS, no frameworks.</textarea>
          <div class="examples">
            <div class="example" data-prompt="A landing page for an indie coffee shop called 'Bean Drop'. Hero with big serif title, opening hours, menu in three columns. Pure HTML/CSS, no frameworks.">Coffee shop landing page</div>
            <div class="example" data-prompt="A markdown preview tool. Textarea on the left, rendered preview on the right, both scroll-synced. Pure HTML/CSS/JS only, write a tiny markdown subset (headings, bold, italic, code, links).">Markdown preview tool</div>
            <div class="example" data-prompt="A persistent todo list using sqlite3 served by a Python http.server-style backend. Add, toggle, delete. Single page, pure CSS, no frameworks.">SQLite todo list</div>
          </div>
          <button id="build">Build &amp; Preview</button>
          <div class="status-row">
            <span class="pulse-dot" id="dot"></span>
            <span id="status"></span>
          </div>
          <div class="sec-note">
            <b>Security model.</b> The OpenAI key lives only here in the
            orchestrator &mdash; it never enters the child sandbox. The sandbox
            has no internet egress (only PyPI/apt mirrors), so a runaway agent
            cannot exfiltrate. Each preview lives ~15 minutes in a disposable
            microVM, then the VM is destroyed.
          </div>
        </section>
        <section class="glass">
          <h2>Build timeline</h2>
          <div class="timeline" id="timeline">
            <div class="empty">Click <b>Build &amp; Preview</b> to watch the agent work.</div>
          </div>
          <div id="preview-host"></div>
        </section>
      </div>
    </main>
    <script>
      const promptEl = document.getElementById("prompt");
      const buildBtn = document.getElementById("build");
      const status = document.getElementById("status");
      const dot = document.getElementById("dot");
      const timeline = document.getElementById("timeline");
      const previewHost = document.getElementById("preview-host");

      document.querySelectorAll(".example").forEach(el => {
        el.addEventListener("click", () => { promptEl.value = el.dataset.prompt; });
      });

      function addStep(label, body) {
        if (timeline.firstChild && timeline.firstChild.classList && timeline.firstChild.classList.contains("empty")) {
          timeline.innerHTML = "";
        }
        const div = document.createElement("div");
        div.className = "step";
        div.innerHTML = `<div class="label"></div><div class="body"></div>`;
        div.querySelector(".label").textContent = label;
        div.querySelector(".body").textContent = body;
        timeline.appendChild(div);
        timeline.scrollTop = timeline.scrollHeight;
      }

      function renderPreview(p) {
        const url = p.url || "";
        const ttl = p.ttl_seconds || 900;
        const expiresAt = Date.now() + ttl * 1000;
        const safeUrl = url.replace(/[<>"']/g, "");
        previewHost.innerHTML = `
          <div class="preview">
            <div class="meta">
              <span class="badge">READY</span>
              <a href="${safeUrl}" target="_blank" rel="noopener">${safeUrl}</a>
              <span class="ttl" id="ttl"></span>
            </div>
            <iframe src="${safeUrl}" loading="lazy" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
          </div>
        `;
        const ttlEl = document.getElementById("ttl");
        function tick() {
          const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
          const m = Math.floor(remaining / 60);
          const s = remaining % 60;
          ttlEl.textContent = `expires in ${m}m ${s.toString().padStart(2, "0")}s`;
          if (remaining > 0) setTimeout(tick, 1000);
          else ttlEl.textContent = "expired";
        }
        tick();
      }

      async function build() {
        buildBtn.disabled = true;
        status.textContent = "Provisioning sandbox\u2026";
        dot.classList.add("active");
        timeline.innerHTML = "";
        previewHost.innerHTML = "";

        let response;
        try {
          response = await fetch("/api/build", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: promptEl.value || "" }),
          });
        } catch (e) {
          status.textContent = "Connection failed.";
          dot.classList.remove("active");
          buildBtn.disabled = false;
          return;
        }
        if (!response.ok) {
          let msg = "Build failed.";
          try { msg = (await response.json()).detail || msg; } catch {}
          status.textContent = msg;
          dot.classList.remove("active");
          buildBtn.disabled = false;
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
          while ((idx = buf.indexOf("\\n\\n")) !== -1) {
            const frame = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const lines = frame.split("\\n");
            let event = "message";
            const data = [];
            for (const line of lines) {
              if (line.startsWith("event:")) event = line.slice(6).trim();
              else if (line.startsWith("data:")) data.push(line.slice(5).trim());
            }
            const payload = data.join("\\n");
            handleEvent(event, payload);
          }
        }
        buildBtn.disabled = false;
        dot.classList.remove("active");
      }

      function handleEvent(event, raw) {
        let data;
        try { data = JSON.parse(raw); } catch { data = { text: raw }; }
        if (event === "phase") {
          status.textContent = data.message || "";
        } else if (event === "tool_called") {
          addStep(`tool: ${data.name || "?"}`, data.args || "");
        } else if (event === "tool_output") {
          addStep("tool output", (data.output || "").slice(0, 800));
        } else if (event === "preview") {
          status.textContent = "Preview ready.";
          renderPreview(data);
        } else if (event === "error") {
          status.textContent = data.message || "Error.";
        } else if (event === "done") {
          if (!status.textContent || /provisioning|running/i.test(status.textContent)) {
            status.textContent = "Done.";
          }
        }
      }

      buildBtn.addEventListener("click", build);
    </script>
  </body>
</html>
"""


app = FastAPI(title="Vibe Preview")

# Track active preview sessions for graceful shutdown.
# {session_id: (client, sandbox, expiry_epoch)}
_active_sessions: dict[str, tuple[InstaVMSandboxClient, Any, float]] = {}
_active_lock = asyncio.Lock()
# Hold strong refs to fire-and-forget cleanup tasks so they aren't GC'd.
_background_tasks: set[asyncio.Task] = set()


@app.on_event("shutdown")
async def _cleanup_active_sessions() -> None:
    async with _active_lock:
        items = list(_active_sessions.items())
        _active_sessions.clear()
    for _, (client, sandbox, _) in items:
        try:
            await client.delete(sandbox)
        except Exception:
            logger.exception("failed to clean up sandbox on shutdown")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/health")
async def health() -> dict[str, str]:
    return {"ok": "true", "runtime": "openai-agents-sandbox", "model": MODEL_NAME}


def _validate_keys() -> tuple[str, str]:
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    instavm_key = (os.environ.get("INSTAVM_API_KEY") or "").strip()
    if not openai_key or looks_like_placeholder_secret(openai_key):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is missing or invalid.")
    if not instavm_key or looks_like_placeholder_secret(instavm_key):
        raise HTTPException(status_code=503, detail="INSTAVM_API_KEY is missing or invalid.")
    return openai_key, instavm_key


def _sse(event: str, data: dict[str, Any] | str) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


async def _delayed_delete(
    client: InstaVMSandboxClient, sandbox: Any, ttl: int
) -> None:
    """Delete the sandbox after the TTL expires. Best effort."""
    try:
        await asyncio.sleep(ttl)
    except asyncio.CancelledError:
        return
    async with _active_lock:
        # Drop tracking entry whose sandbox matches.
        for sid, (_, sb, _) in list(_active_sessions.items()):
            if sb is sandbox:
                _active_sessions.pop(sid, None)
                break
    try:
        await client.delete(sandbox)
    except Exception:
        logger.exception("failed to delete preview sandbox after TTL")


async def _build_stream(prompt: str) -> AsyncIterator[bytes]:
    yield _sse("phase", {"message": "Provisioning sandbox\u2026"})

    manifest = Manifest(
        entries={
            "app/.keep": File(content=b""),
            "app/public/.keep": File(content=b""),
        }
    )

    _, instavm_key = _validate_keys()
    client = InstaVMSandboxClient(api_key=instavm_key)

    sandbox = None
    try:
        sandbox = await client.create(
            manifest=manifest,
            options=InstaVMSandboxClientOptions(
                memory_mb=SANDBOX_MEMORY_MB,
                cpu_count=2,
                timeout=SANDBOX_TIMEOUT,
                exposed_ports=(PREVIEW_PORT,),
                allow_internet_access=False,
                allow_http=False,
                allow_https=False,
                allow_package_managers=True,
            ),
        )
        await sandbox.start()

        yield _sse("phase", {"message": "Sandbox running\u2026"})

        agent = SandboxAgent(
            name="Vibe Builder",
            model=MODEL_NAME,
            instructions=BUILDER_INSTRUCTIONS,
            default_manifest=manifest,
        )

        stream = Runner.run_streamed(
            agent,
            f"Build the following app and start serving it on port 8080:\n\n{prompt}",
            run_config=RunConfig(
                sandbox=SandboxRunConfig(session=sandbox),
                workflow_name="vibe-preview",
            ),
            max_turns=24,
        )

        async for event in stream.stream_events():
            if event.type == "run_item_stream_event":
                if event.name == "tool_called":
                    raw = getattr(event.item, "raw_item", None)
                    name = getattr(raw, "name", "") or "tool"
                    args = ""
                    raw_args = getattr(raw, "arguments", None) or getattr(raw, "args", None)
                    if isinstance(raw_args, str):
                        args = raw_args
                    elif raw_args is not None:
                        try:
                            args = json.dumps(raw_args, default=str)[:1200]
                        except Exception:
                            args = str(raw_args)[:1200]
                    yield _sse("tool_called", {"name": str(name), "args": args[:1200]})
                elif event.name == "tool_output":
                    output = getattr(event.item, "output", "")
                    if not isinstance(output, str):
                        try:
                            output = json.dumps(output, default=str)
                        except Exception:
                            output = str(output)
                    yield _sse("tool_output", {"output": output[:1500]})
            elif event.type == "raw_response_event":
                if isinstance(event.data, ResponseTextDeltaEvent):
                    pass

        endpoint = await sandbox.resolve_exposed_port(PREVIEW_PORT)
        scheme = "https" if endpoint.tls else "http"
        port_part = ""
        if (endpoint.tls and endpoint.port not in (443, None)) or (
            not endpoint.tls and endpoint.port not in (80, None)
        ):
            port_part = f":{endpoint.port}"
        url = f"{scheme}://{endpoint.host}{port_part}"

        sandbox_id = str(id(sandbox))
        async with _active_lock:
            _active_sessions[sandbox_id] = (client, sandbox, time.time() + PREVIEW_TTL_SECONDS)
        task = asyncio.create_task(_delayed_delete(client, sandbox, PREVIEW_TTL_SECONDS))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        sandbox = None  # ownership transferred to the cleanup task

        yield _sse("preview", {"url": url, "ttl_seconds": PREVIEW_TTL_SECONDS})
    except Exception as exc:
        logger.exception("build failed")
        yield _sse("error", {"message": str(exc)[:600]})
        if sandbox is not None:
            try:
                await client.delete(sandbox)
            except Exception:
                logger.exception("failed to clean up sandbox after error")
    finally:
        yield _sse("done", {})


@app.post("/api/build")
async def build(req: BuildRequest) -> StreamingResponse:
    _validate_keys()
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")
    if len(prompt) > 4000:
        raise HTTPException(status_code=413, detail="Prompt exceeds 4000 characters.")
    return StreamingResponse(
        _build_stream(prompt),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
