from __future__ import annotations

import asyncio
import os

import dspy
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

API_BASE = os.environ.get("OPENAI_COMPAT_API_BASE", "https://openrouter.ai/api/v1")
MODEL_NAME = os.environ.get("OPENAI_COMPAT_MODEL", "openai/google/gemma-3n-e4b-it")


class StructuredChat(dspy.Signature):
    """Respond with a concise answer and one sharp follow-up question."""

    question: str = dspy.InputField()
    answer: str = dspy.OutputField(desc="Main response in markdown.")
    follow_up: str = dspy.OutputField(desc="One concrete follow-up question.")


class ChatProgram(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.respond = dspy.ChainOfThought(StructuredChat)

    def forward(self, question: str) -> dspy.Prediction:
        return self.respond(question=question)


app = FastAPI(title="DSPy Hosted Chat")


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>DSPy Hosted Chat</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f7efe6;
        --panel: #fffaf4;
        --ink: #22170f;
        --muted: #716052;
        --accent: #a44d21;
        --accent-soft: #f4dfd0;
        --border: #ead8c9;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Instrument Sans", "Helvetica Neue", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top right, #f9dbc7, transparent 23rem),
          linear-gradient(180deg, #fffdf9, var(--bg));
      }
      main { max-width: 980px; margin: 0 auto; padding: 2rem 1.25rem 3rem; }
      h1 { margin-bottom: 0.45rem; font-size: clamp(2rem, 5vw, 3rem); }
      p { color: var(--muted); line-height: 1.6; }
      .chips { display: flex; gap: 0.7rem; flex-wrap: wrap; margin: 1rem 0 1.4rem; }
      .chip {
        border-radius: 999px;
        padding: 0.35rem 0.75rem;
        background: var(--accent-soft);
        color: var(--accent);
        font-size: 0.92rem;
      }
      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 1rem;
        box-shadow: 0 16px 36px rgba(34, 23, 15, 0.06);
      }
      #thread {
        min-height: 320px;
        display: grid;
        gap: 0.9rem;
        align-content: start;
      }
      .bubble {
        border-radius: 18px;
        padding: 0.9rem 1rem;
        line-height: 1.6;
        white-space: pre-wrap;
      }
      .user { background: #22170f; color: #fff; justify-self: end; max-width: 80%; }
      .assistant { background: #fff3e9; max-width: 100%; }
      textarea {
        width: 100%;
        min-height: 120px;
        margin-top: 1rem;
        border-radius: 16px;
        border: 1px solid var(--border);
        padding: 0.95rem 1rem;
        font: inherit;
        resize: vertical;
      }
      button {
        margin-top: 0.9rem;
        border: 0;
        border-radius: 999px;
        padding: 0.85rem 1.25rem;
        font: inherit;
        font-weight: 700;
        color: #fff;
        cursor: pointer;
        background: var(--accent);
      }
      #status { min-height: 1.4rem; margin-top: 0.7rem; color: var(--accent); font-weight: 600; }
    </style>
  </head>
  <body>
    <main>
      <h1>DSPy Hosted Chat</h1>
      <p>DSPy chat app powered by a hosted model. By default it uses a compact Gemma-family model through OpenRouter, and you can switch models or providers with environment variables.</p>
      <div class="chips">
        <span class="chip">DSPy</span>
        <span class="chip">Hosted model</span>
        <span class="chip">Gemma default</span>
      </div>
      <section class="panel">
        <div id="thread"></div>
        <textarea id="message">Act as a product strategy coach. Compare the tradeoffs of shipping an AI note-taking assistant as a browser extension versus a standalone desktop app.</textarea>
        <button id="send">Send</button>
        <div id="status"></div>
      </section>
    </main>
    <script>
      const thread = document.getElementById("thread");
      const message = document.getElementById("message");
      const status = document.getElementById("status");
      const send = document.getElementById("send");
      const history = [];

      function render(role, text) {
        const node = document.createElement("div");
        node.className = `bubble ${role}`;
        node.textContent = text;
        thread.appendChild(node);
      }

      async function submit() {
        const content = message.value.trim();
        if (!content) return;
        render("user", content);
        history.push({ role: "user", content });
        message.value = "";
        send.disabled = true;
        status.textContent = "Thinking...";
        try {
          const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: content, history }),
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.detail || "Request failed");
          }
          render("assistant", `${payload.answer}\n\nFollow-up: ${payload.follow_up}`);
          history.push({ role: "assistant", content: payload.answer });
          status.textContent = "Ready.";
        } catch (error) {
          status.textContent = String(error);
        } finally {
          send.disabled = false;
        }
      }

      send.addEventListener("click", submit);
    </script>
  </body>
</html>
"""


def configure_lm() -> None:
    api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required.")
    lm = dspy.LM(MODEL_NAME, api_key=api_key, api_base=API_BASE)
    dspy.configure(lm=lm)


def run_program(message: str, history: list[dict[str, str]]) -> dict[str, str]:
    configure_lm()
    transcript = []
    for turn in history[-8:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        transcript.append(f"{role}: {turn.get('content', '').strip()}")
    transcript.append(f"User: {message}")
    prompt = "\n".join(transcript)
    prediction = ChatProgram()(question=prompt)
    return {
        "answer": str(prediction.answer),
        "follow_up": str(prediction.follow_up),
    }


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/health")
async def health() -> dict[str, str]:
    return {"ok": "true", "runtime": "dspy", "model": MODEL_NAME}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")
    try:
        return await asyncio.to_thread(run_program, message, request.history)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"DSPy chat failed: {exc}") from exc
