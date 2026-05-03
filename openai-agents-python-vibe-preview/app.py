from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from agents import RunConfig, Runner
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.entries import File
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
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

# Defensive allowlist for the sandbox endpoint host before we hand the URL
# back to the client. The InstaVM API is the source of truth, but treating
# its output as untrusted keeps a misbehaving control-plane response from
# becoming a `javascript:` or attribute-breakout URL in the browser.
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,253}$")


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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <style>
      :root {
        color-scheme: dark;
        --bg: #08090a;
        --surface: #0f1011;
        --surface-2: #15171a;
        --surface-3: #1a1d21;
        --hover: #1f2227;
        --border: #1f2225;
        --border-strong: #2a2d32;
        --ink: #e8e9ea;
        --ink-2: #c8c9cb;
        --muted: #8a8d92;
        --muted-2: #5b5e63;
        --accent: #a78bfa;
        --accent-bg: rgba(167,139,250,0.10);
        --accent-border: rgba(167,139,250,0.28);
        --success: #4ade80;
        --success-bg: rgba(74,222,128,0.09);
        --success-border: rgba(74,222,128,0.25);
        --danger: #f87171;
        --warn: #fbbf24;
        --info: #60a5fa;
        --radius-sm: 6px;
        --radius: 8px;
        --radius-lg: 12px;
        --shadow-sm: 0 1px 0 rgba(255,255,255,0.04) inset;
      }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      html, body { height: 100%; }
      body {
        font-family: "Inter", -apple-system, system-ui, sans-serif;
        font-size: 14px;
        line-height: 1.5;
        font-feature-settings: "cv11", "ss01", "ss03";
        color: var(--ink);
        background: var(--bg);
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
      }
      main { max-width: 1320px; margin: 0 auto; padding: 32px 24px 64px; }
      header { margin-bottom: 28px; }
      .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; font-size: 13px; color: var(--muted); }
      .brand .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px var(--accent-bg); }
      h1 {
        font-size: 28px; font-weight: 600; letter-spacing: -0.025em;
        color: var(--ink); margin-bottom: 8px;
      }
      .subtitle { color: var(--muted); max-width: 720px; font-size: 14px; }
      .subtitle b { color: var(--ink-2); font-weight: 500; }
      .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 14px; }
      .chip {
        padding: 3px 9px; border-radius: var(--radius-sm); font-size: 12px;
        font-weight: 450; color: var(--muted);
        background: var(--surface-2); border: 1px solid var(--border);
      }
      .grid {
        display: grid; gap: 16px;
        grid-template-columns: minmax(0, 1fr);
      }
      @media (min-width: 1040px) {
        .grid { grid-template-columns: 380px minmax(0, 1fr); }
      }
      .card {
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow-sm);
      }
      .card.input-card { padding: 18px; }
      .card.output-card { padding: 0; overflow: hidden; display: flex; flex-direction: column; min-height: 540px; }
      .panel-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 14px 18px; border-bottom: 1px solid var(--border);
        font-size: 13px; font-weight: 500; color: var(--ink-2);
      }
      .panel-header .meta { color: var(--muted); font-size: 12px; font-weight: 400; }
      h2 { font-size: 13px; font-weight: 500; color: var(--ink-2); margin-bottom: 12px; letter-spacing: -0.005em; }
      label { display: block; font-size: 12px; font-weight: 450; color: var(--muted); margin-bottom: 6px; }
      textarea {
        width: 100%; min-height: 132px; padding: 10px 12px;
        font: inherit; font-size: 13.5px; line-height: 1.5; color: var(--ink);
        background: var(--surface-2); border: 1px solid var(--border);
        border-radius: var(--radius-sm); resize: vertical; outline: none;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
      }
      textarea::placeholder { color: var(--muted-2); }
      textarea:focus { border-color: var(--accent-border); box-shadow: 0 0 0 3px var(--accent-bg); }
      .examples { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
      .example {
        display: flex; align-items: center; gap: 8px;
        padding: 7px 10px; background: transparent; border: 1px solid var(--border);
        border-radius: var(--radius-sm); font-size: 13px; color: var(--muted);
        cursor: pointer; text-align: left;
        transition: color 0.12s ease, border-color 0.12s ease, background 0.12s ease;
      }
      .example:hover { color: var(--ink); border-color: var(--border-strong); background: var(--surface-2); }
      .example::before { content: "→"; color: var(--muted-2); font-weight: 500; }
      .actions { display: flex; align-items: center; gap: 10px; margin-top: 16px; }
      .btn {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 8px 14px; border: 1px solid var(--accent-border);
        border-radius: var(--radius-sm); font: inherit; font-size: 13px; font-weight: 500;
        color: var(--ink); background: var(--accent-bg); cursor: pointer;
        transition: background 0.12s ease, border-color 0.12s ease, transform 0.06s ease;
      }
      .btn:hover:not(:disabled) { background: rgba(167,139,250,0.18); border-color: rgba(167,139,250,0.45); }
      .btn:active:not(:disabled) { transform: translateY(1px); }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .kbd { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11px; color: var(--muted); padding: 1px 5px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface-2); }
      .sec-note {
        margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border);
        font-size: 12px; line-height: 1.55; color: var(--muted);
      }
      .sec-note b { color: var(--ink-2); font-weight: 500; }

      .phases { padding: 14px 18px; border-bottom: 1px solid var(--border); }
      .phases-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
      .phase {
        display: inline-flex; align-items: center; gap: 7px;
        padding: 5px 10px; border-radius: var(--radius-sm);
        font-size: 12.5px; font-weight: 450; color: var(--muted-2);
        background: transparent; border: 1px solid var(--border);
        transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
      }
      .phase[data-status="active"] { color: var(--ink); background: var(--accent-bg); border-color: var(--accent-border); }
      .phase[data-status="done"]   { color: var(--ink-2); background: var(--success-bg); border-color: var(--success-border); }
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
        background: var(--success); border-color: var(--success); opacity: 1;
      }
      .phase[data-status="done"] .ind::after {
        content: ""; position: absolute; left: 3px; top: 0px; width: 4px; height: 7px;
        border: solid #08090a; border-width: 0 1.5px 1.5px 0; transform: rotate(45deg);
      }
      .phase-arrow { color: var(--muted-2); font-size: 11px; user-select: none; }
      @keyframes spin { to { transform: rotate(360deg); } }

      .timeline { flex: 1 1 auto; overflow-y: auto; padding: 4px 0; }
      .timeline::-webkit-scrollbar { width: 8px; }
      .timeline::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 4px; }
      .timeline-empty { padding: 28px 18px; color: var(--muted-2); font-size: 13px; text-align: center; }
      .step {
        display: grid; grid-template-columns: 110px minmax(0, 1fr);
        gap: 14px; align-items: baseline;
        padding: 9px 18px; border-bottom: 1px solid var(--border);
        animation: fadeIn 0.18s ease;
      }
      .step:last-child { border-bottom: 0; }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(2px); } to { opacity: 1; transform: translateY(0); } }
      .step .tag {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 2px 7px; border-radius: 4px;
        font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 11px; font-weight: 500; letter-spacing: 0.01em;
        text-transform: lowercase; line-height: 1.5;
      }
      .step .tag.exec     { background: rgba(167,139,250,0.12); color: var(--accent); }
      .step .tag.write    { background: rgba(74,222,128,0.10); color: var(--success); }
      .step .tag.read     { background: rgba(96,165,250,0.10); color: var(--info); }
      .step .tag.output   { background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }
      .step .tag.system   { background: var(--surface-2); color: var(--muted); }
      .step .body {
        font-family: "JetBrains Mono", ui-monospace, monospace;
        font-size: 12.5px; line-height: 1.55; color: var(--ink-2);
        white-space: pre-wrap; word-break: break-word;
        max-height: 9.5em; overflow: hidden; position: relative;
      }
      .step .body.expanded { max-height: none; }
      .step .body.clipped::after {
        content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 24px;
        background: linear-gradient(to bottom, transparent, var(--surface));
        pointer-events: none;
      }
      .step .body.expanded::after { display: none; }
      .step.click .body { cursor: pointer; }

      .preview-pane {
        margin: 14px 18px 18px; border: 1px solid var(--border); border-radius: var(--radius);
        background: var(--surface-2); overflow: hidden; animation: fadeIn 0.25s ease;
      }
      .preview-pane .meta {
        display: flex; align-items: center; gap: 10px; padding: 10px 14px;
        border-bottom: 1px solid var(--border); font-size: 13px;
      }
      .preview-pane .badge {
        padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500;
        background: var(--success-bg); color: var(--success); border: 1px solid var(--success-border);
        letter-spacing: 0.02em; text-transform: uppercase;
      }
      .preview-pane a { color: var(--ink-2); text-decoration: none; word-break: break-all; flex: 1; }
      .preview-pane a:hover { color: var(--accent); }
      .preview-pane .ttl { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
      .icon-btn {
        display: inline-flex; align-items: center; justify-content: center;
        width: 26px; height: 26px; padding: 0; background: transparent;
        border: 1px solid var(--border); border-radius: 5px; cursor: pointer;
        color: var(--muted); transition: color 0.12s, background 0.12s, border-color 0.12s;
      }
      .icon-btn:hover { color: var(--ink); background: var(--surface-3); border-color: var(--border-strong); }
      .preview-pane iframe {
        display: block; width: 100%; height: 540px; border: 0; background: white;
      }

      .error-banner {
        margin: 14px 18px; padding: 10px 14px;
        background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.28);
        border-radius: var(--radius-sm); color: var(--danger); font-size: 13px;
        font-family: "JetBrains Mono", ui-monospace, monospace;
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <div class="brand"><span class="dot"></span> Vibe Preview &middot; OpenAI Agents SDK on InstaVM</div>
        <h1>Build a small web app from a prompt.</h1>
        <p class="subtitle">The agent scaffolds your app inside a fresh <b>InstaVM</b> microVM, serves it on port 8080, and hands you a public TLS URL backed by an InstaVM share. The model runs in this orchestrator; the sandbox runs the code &mdash; with no API keys and no internet egress.</p>
        <div class="chips">
          <span class="chip">Per-request microVM</span>
          <span class="chip">No keys in sandbox</span>
          <span class="chip">PyPI / apt mirrors only</span>
          <span class="chip">Live TLS share</span>
        </div>
      </header>
      <div class="grid">
        <section class="card input-card">
          <h2>Describe your app</h2>
          <label for="prompt">Prompt</label>
          <textarea id="prompt" placeholder="A retro-styled tip calculator with split-by-N controls, dark mode, and a sticky total card.">A retro-styled tip calculator with split-by-N controls, dark mode, and a sticky total card. Pure HTML/CSS/JS, no frameworks.</textarea>
          <div class="examples">
            <button class="example" data-prompt="A landing page for an indie coffee shop called 'Bean Drop'. Hero with big serif title, opening hours, menu in three columns. Pure HTML/CSS, no frameworks.">Coffee shop landing page</button>
            <button class="example" data-prompt="A markdown preview tool. Textarea on the left, rendered preview on the right, both scroll-synced. Pure HTML/CSS/JS only, write a tiny markdown subset (headings, bold, italic, code, links).">Markdown preview tool</button>
            <button class="example" data-prompt="A persistent todo list using sqlite3 served by a Python http.server-style backend. Add, toggle, delete. Single page, pure CSS, no frameworks.">SQLite todo list</button>
            <button class="example" data-prompt="A FastAPI app with two endpoints: GET / returns a simple HTML page, POST /quote returns a JSON random quote from a list. Install flask or fastapi via pip. Show I can install dependencies.">FastAPI with pip install</button>
          </div>
          <div class="actions">
            <button class="btn" id="build">Build &amp; Preview</button>
            <span class="kbd">&#x2318; Enter</span>
          </div>
          <div class="sec-note">
            <b>Security model.</b> Your <code>OPENAI_API_KEY</code> and <code>INSTAVM_API_KEY</code> stay in this orchestrator. The child sandbox sees only your prompt, has no internet egress, and is destroyed after ~15 minutes.
          </div>
        </section>
        <section class="card output-card">
          <div class="panel-header">
            <span id="output-title">Build timeline</span>
            <span class="meta" id="output-meta"></span>
          </div>
          <div class="phases" id="phases-host" style="display:none;">
            <div class="phases-row" id="phases-row"></div>
          </div>
          <div class="timeline" id="timeline">
            <div class="timeline-empty">Click <b>Build &amp; Preview</b> to watch the agent work.</div>
          </div>
          <div id="preview-host"></div>
          <div id="error-host"></div>
        </section>
      </div>
    </main>
    <script>
      const promptEl = document.getElementById("prompt");
      const buildBtn = document.getElementById("build");
      const timeline = document.getElementById("timeline");
      const phasesHost = document.getElementById("phases-host");
      const phasesRow = document.getElementById("phases-row");
      const previewHost = document.getElementById("preview-host");
      const errorHost = document.getElementById("error-host");
      const outputMeta = document.getElementById("output-meta");

      const phaseEls = new Map();
      let stepCount = 0;
      let runStart = 0;

      function clearEmpty() {
        const e = timeline.querySelector(".timeline-empty");
        if (e) e.remove();
      }

      document.querySelectorAll(".example").forEach(el => {
        el.addEventListener("click", () => { promptEl.value = el.dataset.prompt; promptEl.focus(); });
      });

      promptEl.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !buildBtn.disabled) build();
      });

      function setPhases(phases) {
        phasesRow.innerHTML = "";
        phaseEls.clear();
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

      function updatePhase(id, label, status) {
        const el = phaseEls.get(id);
        if (!el) return;
        el.dataset.status = status;
        if (label) el.querySelector(".lbl").textContent = label;
      }

      function classifyTool(name) {
        const n = String(name).toLowerCase();
        if (n.includes("apply_patch") || n.includes("write") || n.includes("create") || n.includes("edit")) return "write";
        if (n.includes("read") || n.includes("cat") || n.includes("ls") || n.includes("find")) return "read";
        if (n.includes("exec") || n.includes("shell") || n.includes("command") || n.includes("bash")) return "exec";
        return "exec";
      }

      function addStep(kind, tagText, body) {
        clearEmpty();
        const div = document.createElement("div");
        div.className = "step click";
        div.innerHTML = `<span class="tag ${kind}"></span><div class="body clipped"></div>`;
        div.querySelector(".tag").textContent = tagText;
        const bodyEl = div.querySelector(".body");
        bodyEl.textContent = body || "";
        // Only show clip gradient if content actually overflows.
        requestAnimationFrame(() => {
          if (bodyEl.scrollHeight <= bodyEl.clientHeight + 2) bodyEl.classList.remove("clipped");
        });
        div.addEventListener("click", () => {
          bodyEl.classList.toggle("expanded");
          if (bodyEl.classList.contains("expanded")) bodyEl.classList.remove("clipped");
        });
        timeline.appendChild(div);
        stepCount += 1;
        outputMeta.textContent = `${stepCount} step${stepCount === 1 ? "" : "s"}`;
        timeline.scrollTop = timeline.scrollHeight;
      }

      function showError(msg) {
        errorHost.innerHTML = `<div class="error-banner"></div>`;
        errorHost.firstChild.textContent = msg;
      }

      function renderPreview(p) {
        const url = String(p.url || "");
        const ttl = p.ttl_seconds || 900;
        const expiresAt = Date.now() + ttl * 1000;
        if (!/^https?:\\/\\//i.test(url)) {
          showError("Preview URL rejected (unsafe scheme).");
          return;
        }
        const safeUrl = url.replace(/[<>"']/g, "");
        previewHost.innerHTML = `
          <div class="preview-pane">
            <div class="meta">
              <span class="badge">Ready</span>
              <a href="${safeUrl}" target="_blank" rel="noopener">${safeUrl}</a>
              <span class="ttl" id="ttl"></span>
              <button class="icon-btn" id="copy-btn" title="Copy URL">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
              </button>
              <a class="icon-btn" href="${safeUrl}" target="_blank" rel="noopener" title="Open in new tab">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              </a>
            </div>
            <iframe src="${safeUrl}" loading="lazy" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
          </div>
        `;
        document.getElementById("copy-btn").addEventListener("click", () => {
          navigator.clipboard?.writeText(safeUrl);
        });
        const ttlEl = document.getElementById("ttl");
        function tick() {
          const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
          const m = Math.floor(remaining / 60);
          const s = remaining % 60;
          ttlEl.textContent = `${m}:${s.toString().padStart(2, "0")} left`;
          if (remaining > 0) setTimeout(tick, 1000);
          else ttlEl.textContent = "expired";
        }
        tick();
      }

      function resetUI() {
        timeline.innerHTML = "";
        previewHost.innerHTML = "";
        errorHost.innerHTML = "";
        phasesRow.innerHTML = "";
        phasesHost.style.display = "none";
        phaseEls.clear();
        stepCount = 0;
        outputMeta.textContent = "";
        const empty = document.createElement("div");
        empty.className = "timeline-empty";
        empty.textContent = "Connecting\u2026";
        timeline.appendChild(empty);
      }

      async function build() {
        if (!promptEl.value.trim()) { promptEl.focus(); return; }
        buildBtn.disabled = true;
        resetUI();
        runStart = Date.now();

        let response;
        try {
          response = await fetch("/api/build", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: promptEl.value }),
          });
        } catch (e) {
          showError("Connection failed. Is the orchestrator reachable?");
          buildBtn.disabled = false;
          return;
        }
        if (!response.ok) {
          let msg = "Build failed.";
          try { msg = (await response.json()).detail || msg; } catch {}
          showError(msg);
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
            handleEvent(event, data.join("\\n"));
          }
        }
        buildBtn.disabled = false;
        const sec = ((Date.now() - runStart) / 1000).toFixed(1);
        outputMeta.textContent = `${stepCount} step${stepCount === 1 ? "" : "s"} \u00B7 ${sec}s`;
      }

      function handleEvent(event, raw) {
        let data;
        try { data = JSON.parse(raw); } catch { data = { text: raw }; }
        if (event === "phases") {
          setPhases(data.phases || []);
          clearEmpty();
        } else if (event === "phase") {
          updatePhase(data.id, data.label, data.status);
        } else if (event === "tool_called") {
          const kind = classifyTool(data.name);
          addStep(kind, data.name || "tool", data.args || "");
        } else if (event === "tool_output") {
          addStep("output", "output", (data.output || "").slice(0, 1500));
        } else if (event === "preview") {
          renderPreview(data);
        } else if (event === "error") {
          showError(data.message || "Build failed.");
          phaseEls.forEach((el) => {
            if (el.dataset.status === "active") el.dataset.status = "error";
          });
        }
      }

      buildBtn.addEventListener("click", build);
    </script>
  </body>
</html>
"""


# Track active preview sessions so we can release them on shutdown.
# {session_id: (client, sandbox)}
_active_sessions: dict[str, tuple[InstaVMSandboxClient, Any]] = {}
_active_lock = asyncio.Lock()
# Hold strong refs to fire-and-forget cleanup tasks so they aren't GC'd.
_background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    async with _active_lock:
        items = list(_active_sessions.values())
        _active_sessions.clear()
    for client, sandbox in items:
        try:
            await client.delete(sandbox)
        except Exception:
            logger.exception("failed to clean up sandbox on shutdown")


app = FastAPI(title="Vibe Preview", lifespan=_lifespan)


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


def _phase(phase_id: str, label: str, status: str, **extra: Any) -> bytes:
    """Emit an SSE phase event with a stable id + status the UI can track.

    status: "active" | "done" | "error". The UI keeps a list of phase ids
    in declaration order and renders each as a step in the tracker.
    """
    payload: dict[str, Any] = {"id": phase_id, "label": label, "status": status}
    if extra:
        payload.update(extra)
    return _sse("phase", payload)


HEARTBEAT_INTERVAL_S = float(os.environ.get("VIBE_SSE_HEARTBEAT_S", "8"))


async def _with_heartbeats(
    inner: AsyncIterator[bytes], interval: float = HEARTBEAT_INTERVAL_S
) -> AsyncIterator[bytes]:
    """Inject SSE heartbeat frames so reverse proxies don't 502 long agent runs."""
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
                await queue.put(_sse("done", {}))
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


async def _delayed_delete(
    client: InstaVMSandboxClient, sandbox: Any, ttl: int
) -> None:
    """Delete the sandbox after the TTL expires. Best effort."""
    try:
        await asyncio.sleep(ttl)
    except asyncio.CancelledError:
        return
    async with _active_lock:
        for sid, (_, sb) in list(_active_sessions.items()):
            if sb is sandbox:
                _active_sessions.pop(sid, None)
                break
    try:
        await client.delete(sandbox)
    except Exception:
        logger.exception("failed to delete preview sandbox after TTL")


async def _build_stream(prompt: str) -> AsyncIterator[bytes]:
    # Declare phases up front so the UI can render the full tracker
    # immediately, even before any of them is active.
    yield _sse(
        "phases",
        {
            "phases": [
                {"id": "provision", "label": "Provision sandbox"},
                {"id": "boot", "label": "Boot microVM"},
                {"id": "build", "label": "Build app"},
                {"id": "preview", "label": "Start preview"},
            ]
        },
    )
    yield _phase("provision", "Provision sandbox", "active")

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
        yield _phase("provision", "Provision sandbox", "done")
        yield _phase("boot", "Boot microVM", "active")

        await sandbox.start()

        yield _phase("boot", "Boot microVM", "done")
        yield _phase("build", "Build app", "active")

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

        yield _phase("build", "Build app", "done")
        yield _phase("preview", "Start preview", "active")

        endpoint = await sandbox.resolve_exposed_port(PREVIEW_PORT)
        scheme = "https" if endpoint.tls else "http"
        if scheme not in ("http", "https"):
            raise RuntimeError(f"unexpected sandbox endpoint scheme: {scheme!r}")
        if not _HOSTNAME_RE.match(endpoint.host or ""):
            raise RuntimeError(f"unexpected sandbox endpoint host: {endpoint.host!r}")
        port_part = ""
        if (endpoint.tls and endpoint.port not in (443, None)) or (
            not endpoint.tls and endpoint.port not in (80, None)
        ):
            port_part = f":{endpoint.port}"
        url = f"{scheme}://{endpoint.host}{port_part}"

        sandbox_id = str(id(sandbox))
        async with _active_lock:
            _active_sessions[sandbox_id] = (client, sandbox)
        task = asyncio.create_task(_delayed_delete(client, sandbox, PREVIEW_TTL_SECONDS))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        sandbox = None  # ownership transferred to the cleanup task

        yield _phase("preview", "Start preview", "done")
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
        _with_heartbeats(_build_stream(prompt)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
