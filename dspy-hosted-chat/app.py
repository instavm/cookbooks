from __future__ import annotations

import asyncio
import os

import dspy
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

API_BASE = os.environ.get("OPENAI_COMPAT_API_BASE", "https://openrouter.ai/api/v1")
MODEL_NAME = os.environ.get("OPENAI_COMPAT_MODEL", "openai/google/gemma-3n-e4b-it")
REQUEST_TIMEOUT_SECONDS = 45


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


app = FastAPI(title="DSPy Chat")


def friendly_provider_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()
    if (
        "api key" in lower
        or "authentication" in lower
        or "missing authentication" in lower
        or "unauthorized" in lower
        or "invalid" in lower and "key" in lower
        or "openrouter_api_key" in lower
    ):
        return "Model credentials are invalid or missing for this deployment. Add a valid OPENROUTER_API_KEY and redeploy."
    if "timeout" in lower or "timed out" in lower:
        return "The model provider took too long to respond. Try again in a moment."
    if "server disconnected" in lower or "connection" in lower or "proxy error" in lower:
        return "The model provider closed the request before returning a response. Verify the deployment credentials and try again."
    return "The model request failed for this deployment. Verify the configured credentials and try again."


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>DSPy Chat</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
    <style>
      :root {
        color-scheme: dark;
        --bg: #110e0a;
        --surface: rgba(28, 20, 14, 0.55);
        --glass: rgba(36, 26, 18, 0.45);
        --ink: #f0e8e0;
        --muted: #a89484;
        --accent: #f59e0b;
        --accent-dim: rgba(245, 158, 11, 0.12);
        --accent-glow: rgba(245, 158, 11, 0.25);
        --border: rgba(245, 158, 11, 0.14);
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
          radial-gradient(ellipse 65% 45% at 80% 10%, rgba(245,158,11,0.08), transparent),
          radial-gradient(ellipse 55% 40% at 20% 85%, rgba(217,119,6,0.06), transparent),
          radial-gradient(ellipse 45% 45% at 50% 50%, rgba(120,53,15,0.08), transparent);
      }
      main { max-width: 720px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
      h1 {
        font-family: "Space Grotesk", sans-serif;
        font-size: clamp(2rem, 5vw, 2.8rem);
        font-weight: 700;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #f0e8e0 30%, var(--accent));
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
      }
      .glass {
        background: var(--glass);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1.25rem;
        backdrop-filter: blur(18px) saturate(1.4);
        -webkit-backdrop-filter: blur(18px) saturate(1.4);
        box-shadow: 0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.04);
      }
      #thread {
        min-height: 320px;
        max-height: 520px;
        overflow-y: auto;
        display: grid;
        gap: 0.75rem;
        align-content: start;
        padding-bottom: 0.5rem;
      }
      #thread::-webkit-scrollbar { width: 5px; }
      #thread::-webkit-scrollbar-track { background: transparent; }
      #thread::-webkit-scrollbar-thumb { background: rgba(245,158,11,0.2); border-radius: 4px; }
      .bubble {
        border-radius: 16px;
        padding: 0.8rem 1rem;
        line-height: 1.65;
        white-space: pre-wrap;
        font-size: 0.9rem;
        animation: slideIn 0.3s cubic-bezier(.4,0,.2,1);
      }
      @keyframes slideIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .user {
        background: linear-gradient(135deg, #d97706, #b45309);
        color: #fff;
        justify-self: end;
        max-width: 82%;
        box-shadow: 0 2px 12px rgba(217,119,6,0.25);
      }
      .assistant {
        background: rgba(42, 30, 20, 0.7);
        color: var(--ink);
        max-width: 100%;
        border: 1px solid rgba(245,158,11,0.08);
      }
      .follow-up-callout {
        margin-top: 0.6rem;
        padding: 0.65rem 0.85rem;
        border-radius: 10px;
        border-left: 3px solid var(--accent);
        background: var(--accent-dim);
        color: var(--accent);
        font-size: 0.85rem;
        font-weight: 500;
        line-height: 1.55;
      }
      .typing-indicator {
        display: none;
        gap: 4px;
        padding: 0.8rem 1rem;
        border-radius: 16px;
        background: rgba(42, 30, 20, 0.7);
        border: 1px solid rgba(245,158,11,0.08);
        width: fit-content;
        animation: slideIn 0.3s cubic-bezier(.4,0,.2,1);
      }
      .typing-indicator.active { display: flex; }
      .typing-indicator span {
        width: 7px; height: 7px; border-radius: 50%;
        background: var(--accent);
        animation: typingBounce 1.2s ease-in-out infinite;
      }
      .typing-indicator span:nth-child(2) { animation-delay: 0.15s; }
      .typing-indicator span:nth-child(3) { animation-delay: 0.3s; }
      @keyframes typingBounce {
        0%,60%,100% { opacity: 0.3; transform: translateY(0); }
        30% { opacity: 1; transform: translateY(-4px); }
      }
      textarea {
        width: 100%;
        min-height: 100px;
        margin-top: 0.75rem;
        border-radius: 12px;
        border: 1px solid var(--border);
        padding: 0.85rem 1rem;
        font: inherit;
        font-size: 0.92rem;
        resize: vertical;
        background: rgba(0,0,0,0.3);
        color: var(--ink);
        outline: none;
        transition: border-color 0.25s, box-shadow 0.25s;
      }
      textarea:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px var(--accent-glow);
      }
      button {
        margin-top: 0.75rem;
        border: 0;
        border-radius: 999px;
        padding: 0.7rem 1.4rem;
        font: inherit;
        font-weight: 600;
        font-size: 0.9rem;
        color: #110e0a;
        cursor: pointer;
        background: linear-gradient(135deg, #f59e0b, #d97706);
        box-shadow: 0 2px 12px rgba(245,158,11,0.3);
        transition: transform 0.2s cubic-bezier(.4,0,.2,1), box-shadow 0.2s;
      }
      button:hover:not(:disabled) {
        transform: translateY(-1px) scale(1.02);
        box-shadow: 0 4px 20px rgba(245,158,11,0.4);
      }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
      .status-row { display: flex; align-items: center; gap: 0.45rem; min-height: 1.4rem; margin-top: 0.6rem; }
      #status { font-weight: 600; font-size: 0.85rem; color: var(--accent); }
      @media (max-width: 600px) { main { padding: 1.5rem 1rem 2.5rem; } }
    </style>
  </head>
  <body>
    <main>
      <h1>DSPy Chat</h1>
      <p class="subtitle">Ask for product strategy, positioning, or tradeoff advice. Replies come back as a concise answer plus one sharp follow-up question.</p>
      <div class="chips">
        <span class="chip">DSPy</span>
        <span class="chip">Structured replies</span>
        <span class="chip">Gemma-family default</span>
      </div>
      <section class="glass">
        <div id="thread">
          <div class="typing-indicator" id="typing"><span></span><span></span><span></span></div>
        </div>
        <textarea id="message">Act as a product strategy coach. Compare the tradeoffs of shipping an AI note-taking assistant as a browser extension versus a standalone desktop app.</textarea>
        <button id="send">Send</button>
        <div class="status-row">
          <span id="status"></span>
        </div>
      </section>
    </main>
    <script>
      const thread = document.getElementById("thread");
      const typing = document.getElementById("typing");
      const message = document.getElementById("message");
      const status = document.getElementById("status");
      const send = document.getElementById("send");
      const history = [];

      function render(role, text, followUp) {
        const node = document.createElement("div");
        node.className = "bubble " + role;
        node.textContent = text;
        thread.insertBefore(node, typing);
        if (followUp) {
          const callout = document.createElement("div");
          callout.className = "follow-up-callout";
          callout.textContent = followUp;
          node.appendChild(callout);
        }
        thread.scrollTop = thread.scrollHeight;
      }

      async function submit() {
        const content = message.value.trim();
        if (!content) return;
        render("user", content);
        history.push({ role: "user", content: content });
        message.value = "";
        send.disabled = true;
        status.textContent = "Thinking\u2026";
        typing.classList.add("active");
        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 45000);
        try {
          const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: content, history: history }),
            signal: controller.signal,
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.detail || "Request failed");
          }
          typing.classList.remove("active");
          render("assistant", payload.answer, payload.follow_up);
          history.push({ role: "assistant", content: payload.answer });
          status.textContent = "Ready.";
        } catch (error) {
          typing.classList.remove("active");
          if (error instanceof DOMException && error.name === "AbortError") {
            status.textContent = "The model took too long to respond. Try again.";
          } else {
            status.textContent = error instanceof Error ? error.message : String(error);
          }
        } finally {
          window.clearTimeout(timeoutId);
          send.disabled = false;
        }
      }

      send.addEventListener("click", submit);
      message.addEventListener("keydown", function(e) {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
      });
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
        return await asyncio.wait_for(
            asyncio.to_thread(run_program, message, request.history),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="The model provider took too long to respond. Try again in a moment.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=friendly_provider_error(exc)) from exc
