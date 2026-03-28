from __future__ import annotations

import os

from agents import Agent, Runner, WebSearchTool
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

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


class ReportRequest(BaseModel):
    query: str


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Research Desk</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f4f1ea;
        --panel: #fffdf8;
        --ink: #152313;
        --muted: #66745f;
        --accent: #1d6b52;
        --accent-2: #d7efe3;
        --border: #d5ddcf;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
        background:
          radial-gradient(circle at top right, #d5efe4, transparent 28rem),
          linear-gradient(180deg, #fbfaf7, var(--bg));
        color: var(--ink);
      }
      main { max-width: 960px; margin: 0 auto; padding: 2rem 1.25rem 3rem; }
      h1 { margin-bottom: 0.5rem; font-size: clamp(2rem, 5vw, 3rem); }
      p { color: var(--muted); line-height: 1.55; }
      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 1rem;
        box-shadow: 0 16px 36px rgba(21, 35, 19, 0.07);
      }
      textarea {
        width: 100%;
        min-height: 140px;
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 0.9rem 1rem;
        font: inherit;
        resize: vertical;
        background: #fff;
      }
      button {
        margin-top: 0.9rem;
        border: 0;
        border-radius: 999px;
        padding: 0.85rem 1.2rem;
        font: inherit;
        font-weight: 600;
        cursor: pointer;
        color: #fff;
        background: var(--accent);
      }
      pre {
        margin: 0;
        white-space: pre-wrap;
        line-height: 1.55;
        font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      }
      .grid { display: grid; gap: 1rem; margin-top: 1.25rem; }
      .meta { display: flex; gap: 0.75rem; flex-wrap: wrap; margin: 1rem 0; }
      .chip {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        border-radius: 999px;
        padding: 0.35rem 0.7rem;
        background: var(--accent-2);
        color: var(--accent);
        font-size: 0.9rem;
      }
      #status { min-height: 1.5rem; font-weight: 600; color: var(--accent); }
      @media (min-width: 900px) { .grid { grid-template-columns: 1.2fr 1fr; } }
    </style>
  </head>
  <body>
    <main>
      <h1>Research Desk</h1>
      <p>Ask for a market brief, company update, product scan, or technical summary. The app gathers supporting notes and turns them into a concise memo.</p>
      <div class="meta">
        <span class="chip">OpenAI Agents</span>
        <span class="chip">Web search grounded</span>
        <span class="chip">Briefing generator</span>
      </div>
      <section class="panel">
        <label for="query"><strong>Research prompt</strong></label>
        <textarea id="query">Summarize the latest AI browser agents landscape, key product themes, and notable open questions.</textarea>
        <button id="run">Generate briefing</button>
        <div id="status"></div>
      </section>
      <section class="grid">
        <article class="panel">
          <h2>Briefing</h2>
          <pre id="report">Run a query to generate a research memo.</pre>
        </article>
        <article class="panel">
          <h2>Research Notes</h2>
          <pre id="notes">The analyst pass will appear here.</pre>
        </article>
      </section>
    </main>
    <script>
      const query = document.getElementById("query");
      const status = document.getElementById("status");
      const notes = document.getElementById("notes");
      const report = document.getElementById("report");
      const run = document.getElementById("run");

      async function submit() {
        status.textContent = "Researching...";
        run.disabled = true;
        notes.textContent = "";
        report.textContent = "";
        try {
          const response = await fetch("/api/report", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query.value }),
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.detail || "Request failed");
          }
          notes.textContent = payload.notes;
          report.textContent = payload.report;
          status.textContent = "Done.";
        } catch (error) {
          status.textContent = String(error);
        } finally {
          run.disabled = false;
        }
      }

      run.addEventListener("click", submit);
    </script>
  </body>
</html>
"""


async def build_report(query: str) -> dict[str, str]:
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
        payload = await build_report(query)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Research run failed: {exc}") from exc
    return {"query": query, **payload}
