from __future__ import annotations

import asyncio
import os

from agents import Agent, Runner, WebSearchTool
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
REQUEST_TIMEOUT_SECONDS = 60


def looks_like_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    return any(
        marker in normalized
        for marker in ("dummy", "test", "placeholder", "your_key", "your-api-key", "changeme", "example")
    )

research_agent = Agent(
    name="research_analyst",
    model=MODEL_NAME,
    instructions=(
        "You are a practical research analyst. Use web search when it helps. "
        "Return 5-7 short evidence bullets with source cues, notable risks, and what still needs verification."
    ),
    tools=[WebSearchTool()],
)

writer_agent = Agent(
    name="memo_writer",
    model=MODEL_NAME,
    instructions=(
        "You write concise but useful markdown briefings. Produce sections for "
        "Executive Summary, Key Findings, Risks, and Follow-up Questions."
    ),
)

app = FastAPI(title="Research Desk")


def friendly_provider_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()
    if (
        "api key" in lower
        or "authentication" in lower
        or "unauthorized" in lower
        or "missing authentication" in lower
        or "invalid" in lower and "key" in lower
    ):
        return "OpenAI credentials are invalid or missing for this deployment. Add a valid OPENAI_API_KEY and redeploy."
    if "timeout" in lower or "timed out" in lower:
        return "OpenAI took too long to respond. Try again in a moment."
    if "server disconnected" in lower or "connection" in lower or "proxy error" in lower:
        return "OpenAI closed the request before returning a response. Verify the deployment credentials and try again."
    return "The OpenAI request failed for this deployment. Verify the configured credentials and try again."


class ReportRequest(BaseModel):
    query: str


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Research Desk</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
    <style>
      :root {
        color-scheme: dark;
        --bg: #0c1210;
        --surface: rgba(16, 32, 26, 0.55);
        --glass: rgba(22, 44, 36, 0.42);
        --ink: #e8f0ec;
        --muted: #8fa89a;
        --accent: #34d399;
        --accent-dim: rgba(52, 211, 153, 0.12);
        --accent-glow: rgba(52, 211, 153, 0.25);
        --border: rgba(52, 211, 153, 0.14);
        --radius: 16px;
      }
      * { box-sizing: border-box; margin: 0; }
      body {
        font-family: "Inter", system-ui, sans-serif;
        color: var(--ink);
        background: var(--bg);
        min-height: 100vh;
        overflow-x: hidden;
      }
      body::before {
        content: "";
        position: fixed; inset: 0; z-index: -1;
        background:
          radial-gradient(ellipse 70% 50% at 20% 10%, rgba(52,211,153,0.10), transparent),
          radial-gradient(ellipse 60% 40% at 80% 85%, rgba(16,185,129,0.08), transparent),
          radial-gradient(ellipse 50% 50% at 50% 50%, rgba(6,78,59,0.12), transparent);
      }
      main { max-width: 980px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
      h1 {
        font-family: "Space Grotesk", sans-serif;
        font-size: clamp(2rem, 5vw, 2.8rem);
        font-weight: 700;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #e8f0ec 30%, var(--accent));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      .subtitle { color: var(--muted); line-height: 1.6; margin-top: 0.5rem; font-size: 0.95rem; }
      .chips { display: flex; gap: 0.6rem; flex-wrap: wrap; margin: 1.2rem 0 1.6rem; }
      .chip {
        border-radius: 999px;
        padding: 0.3rem 0.75rem;
        background: var(--accent-dim);
        color: var(--accent);
        font-size: 0.82rem;
        font-weight: 500;
        border: 1px solid var(--border);
        letter-spacing: 0.01em;
      }
      .glass {
        background: var(--glass);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.25rem;
        backdrop-filter: blur(18px) saturate(1.4);
        -webkit-backdrop-filter: blur(18px) saturate(1.4);
        box-shadow: 0 8px 32px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.04);
      }
      label { font-weight: 500; font-size: 0.88rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
      textarea {
        width: 100%;
        min-height: 120px;
        margin-top: 0.6rem;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        font: inherit;
        font-size: 0.92rem;
        resize: vertical;
        background: rgba(0,0,0,0.3);
        color: var(--ink);
        transition: border-color 0.25s, box-shadow 0.25s;
        outline: none;
      }
      textarea:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px var(--accent-glow);
      }
      button {
        margin-top: 0.9rem;
        border: 0;
        border-radius: 999px;
        padding: 0.75rem 1.5rem;
        font: inherit;
        font-weight: 600;
        font-size: 0.9rem;
        cursor: pointer;
        color: #0c1210;
        background: linear-gradient(135deg, #34d399, #10b981);
        box-shadow: 0 2px 12px rgba(52,211,153,0.3);
        transition: transform 0.2s cubic-bezier(.4,0,.2,1), box-shadow 0.2s;
      }
      button:hover:not(:disabled) {
        transform: translateY(-1px) scale(1.02);
        box-shadow: 0 4px 20px rgba(52,211,153,0.4);
      }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
      .status-row { display: flex; align-items: center; gap: 0.5rem; min-height: 1.5rem; margin-top: 0.7rem; }
      #status { font-weight: 600; font-size: 0.88rem; color: var(--accent); }
      .pulse-dot {
        width: 8px; height: 8px; border-radius: 50%; background: var(--accent);
        display: none;
        animation: pulse 1.4s ease-in-out infinite;
      }
      .pulse-dot.active { display: block; }
      @keyframes pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.75); } }
      .grid { display: grid; gap: 1rem; margin-top: 1.25rem; }
      .grid .glass { transition: opacity 0.4s ease, transform 0.4s ease; }
      .grid .glass.loading { opacity: 0.5; }
      h2 {
        font-family: "Space Grotesk", sans-serif;
        font-size: 1.05rem;
        font-weight: 600;
        margin-bottom: 0.75rem;
        color: var(--accent);
        letter-spacing: -0.01em;
      }
      pre {
        margin: 0;
        white-space: pre-wrap;
        line-height: 1.65;
        font-family: "SF Mono", "Fira Code", monospace;
        font-size: 0.85rem;
        color: var(--muted);
      }
      pre.has-content { color: var(--ink); }
      .shimmer {
        background: linear-gradient(90deg, transparent, rgba(52,211,153,0.06), transparent);
        background-size: 200% 100%;
        animation: shimmer 1.8s ease-in-out infinite;
      }
      @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
      @media (min-width: 900px) { .grid { grid-template-columns: 1.2fr 1fr; } }
      @media (max-width: 600px) { main { padding: 1.5rem 1rem 2.5rem; } }
    </style>
  </head>
  <body>
    <main>
      <h1>Research Desk</h1>
      <p class="subtitle">Ask for a market brief, company update, product scan, or technical summary. The app gathers supporting notes and turns them into a concise memo.</p>
      <div class="chips">
        <span class="chip">OpenAI Agents</span>
        <span class="chip">Web search grounded</span>
        <span class="chip">Briefing generator</span>
      </div>
      <section class="glass">
        <label for="query">Research prompt</label>
        <textarea id="query">Summarize the latest AI browser agents landscape, key product themes, and notable open questions.</textarea>
        <button id="run">Generate briefing</button>
        <div class="status-row">
          <span class="pulse-dot" id="dot"></span>
          <span id="status"></span>
        </div>
      </section>
      <section class="grid">
        <article class="glass" id="briefing-panel">
          <h2>Briefing</h2>
          <pre id="report">Run a query to generate a research memo.</pre>
        </article>
        <article class="glass" id="notes-panel">
          <h2>Research Notes</h2>
          <pre id="notes">The analyst pass will appear here.</pre>
        </article>
      </section>
    </main>
    <script>
      const query = document.getElementById("query");
      const status = document.getElementById("status");
      const dot = document.getElementById("dot");
      const notes = document.getElementById("notes");
      const report = document.getElementById("report");
      const run = document.getElementById("run");
      const briefingPanel = document.getElementById("briefing-panel");
      const notesPanel = document.getElementById("notes-panel");

      async function submit() {
        status.textContent = "Researching\u2026";
        dot.classList.add("active");
        run.disabled = true;
        notes.textContent = "";
        notes.className = "shimmer";
        report.textContent = "";
        report.className = "shimmer";
        briefingPanel.classList.add("loading");
        notesPanel.classList.add("loading");
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 60000);
        try {
          const response = await fetch("/api/report", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query.value }),
            signal: controller.signal,
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.detail || "Request failed");
          }
          notes.className = "has-content";
          report.className = "has-content";
          notes.textContent = payload.notes;
          report.textContent = payload.report;
          briefingPanel.classList.remove("loading");
          notesPanel.classList.remove("loading");
          status.textContent = "Done.";
          dot.classList.remove("active");
        } catch (error) {
          notes.className = "";
          report.className = "";
          briefingPanel.classList.remove("loading");
          notesPanel.classList.remove("loading");
          if (error instanceof DOMException && error.name === "AbortError") {
            status.textContent = "OpenAI took too long to respond. Try again.";
          } else {
            status.textContent = error instanceof Error ? error.message : String(error);
          }
          dot.classList.remove("active");
        } finally {
          window.clearTimeout(timeoutId);
          run.disabled = false;
        }
      }

      run.addEventListener("click", submit);
    </script>
  </body>
</html>
"""


async def build_report(query: str) -> dict[str, str]:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")
    if looks_like_placeholder_secret(api_key):
        raise RuntimeError("OPENAI_API_KEY is invalid or still set to a placeholder value.")
    notes_result = await Runner.run(
        research_agent,
        (
            f"User question: {query}\n"
            "Research this topic. Return concise notes with direct evidence, source cues, and risks."
        ),
    )
    notes = str(notes_result.final_output)
    report_result = await Runner.run(
        writer_agent,
        (
            f"Original question: {query}\n\n"
            f"Research notes:\n{notes}\n\n"
            "Write a useful markdown briefing for a product or engineering audience."
        ),
    )
    return {"notes": notes, "report": str(report_result.final_output)}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/health")
async def health() -> dict[str, str]:
    return {"ok": "true", "runtime": "openai-agents", "model": MODEL_NAME}


@app.post("/api/report")
async def create_report(request: ReportRequest) -> dict[str, str]:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required.")
    try:
        payload = await asyncio.wait_for(build_report(query), timeout=REQUEST_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="OpenAI took too long to respond. Try again in a moment.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=friendly_provider_error(exc)) from exc
    return {"query": query, **payload}
