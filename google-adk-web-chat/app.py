from __future__ import annotations

import datetime as dt
import asyncio
import os
import uuid
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from pydantic import BaseModel, Field

if os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]

MODEL_NAME = os.environ.get("GOOGLE_MODEL", "gemini-2.5-flash")
APP_NAME = "instavm-google-adk-web-chat"
REQUEST_TIMEOUT_SECONDS = 45


def get_weather(location: str) -> str:
    city = location.lower().strip()
    if "tokyo" in city:
        return "Tokyo is mild today with light clouds and a high near 19C."
    if "london" in city:
        return "London is cool with intermittent showers and a high near 12C."
    if "san francisco" in city or "sf" in city:
        return "San Francisco is breezy and foggy with a high near 15C."
    return f"No live weather feed is connected. Use {location!r} as a planning placeholder."


def get_current_time(location: str) -> str:
    city = location.lower().strip()
    if "tokyo" in city:
        zone = "Asia/Tokyo"
    elif "london" in city:
        zone = "Europe/London"
    elif "san francisco" in city or "sf" in city:
        zone = "America/Los_Angeles"
    else:
        return f"I do not have a timezone mapping for {location!r}."
    now = dt.datetime.now(ZoneInfo(zone))
    return f"The current time in {location} is {now.strftime('%Y-%m-%d %H:%M %Z')}."


root_agent = Agent(
    name="city_concierge",
    model=MODEL_NAME,
    description="A travel and city-planning assistant with lightweight time and weather tools.",
    instruction=(
        "You are a polished city concierge for founders, operators, and travelers. "
        "Use the tools when weather or current local time would materially improve the answer. "
        "Give concise but concrete recommendations with tradeoffs and next steps."
    ),
    tools=[get_weather, get_current_time],
)

app = FastAPI(title="City Guide")


def friendly_provider_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()
    if (
        "api key" in lower
        or "api_key" in lower
        or "gemini_api_key" in lower
        or "unauthenticated" in lower
        or "permission denied" in lower
        or "invalid" in lower and "key" in lower
        or "authentication" in lower
    ):
        return "Gemini credentials are invalid or missing for this deployment. Add a valid GOOGLE_API_KEY and redeploy."
    if "timeout" in lower or "timed out" in lower:
        return "Gemini took too long to respond. Try again in a moment."
    if "server disconnected" in lower or "connection" in lower or "proxy error" in lower:
        return "Gemini closed the request before returning a response. Verify the deployment credentials and try again."
    return "The Gemini request failed for this deployment. Verify the configured credentials and try again."


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = Field(default_factory=list)


HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>City Guide</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
    <style>
      :root {
        color-scheme: dark;
        --bg: #0a0f1a;
        --surface: rgba(14, 22, 42, 0.55);
        --glass: rgba(18, 30, 58, 0.45);
        --ink: #e4eaf4;
        --muted: #8896ad;
        --accent: #60a5fa;
        --accent-dim: rgba(96, 165, 250, 0.12);
        --accent-glow: rgba(96, 165, 250, 0.25);
        --border: rgba(96, 165, 250, 0.14);
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
          radial-gradient(ellipse 65% 45% at 15% 8%, rgba(96,165,250,0.10), transparent),
          radial-gradient(ellipse 55% 40% at 85% 80%, rgba(59,130,246,0.08), transparent),
          radial-gradient(ellipse 45% 45% at 50% 50%, rgba(30,58,138,0.10), transparent);
      }
      main { max-width: 720px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
      h1 {
        font-family: "Space Grotesk", sans-serif;
        font-size: clamp(2rem, 5vw, 2.8rem);
        font-weight: 700;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #e4eaf4 30%, var(--accent));
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
        min-height: 340px;
        max-height: 520px;
        overflow-y: auto;
        display: grid;
        gap: 0.75rem;
        align-content: start;
        padding-bottom: 0.5rem;
      }
      #thread::-webkit-scrollbar { width: 5px; }
      #thread::-webkit-scrollbar-track { background: transparent; }
      #thread::-webkit-scrollbar-thumb { background: rgba(96,165,250,0.2); border-radius: 4px; }
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
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: #fff;
        justify-self: end;
        max-width: 82%;
        box-shadow: 0 2px 12px rgba(59,130,246,0.25);
      }
      .assistant {
        background: rgba(30, 41, 59, 0.7);
        color: var(--ink);
        max-width: 100%;
        border: 1px solid rgba(96,165,250,0.08);
      }
      .typing-indicator {
        display: none;
        gap: 4px;
        padding: 0.8rem 1rem;
        border-radius: 16px;
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(96,165,250,0.08);
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
        color: #fff;
        cursor: pointer;
        background: linear-gradient(135deg, #60a5fa, #3b82f6);
        box-shadow: 0 2px 12px rgba(96,165,250,0.3);
        transition: transform 0.2s cubic-bezier(.4,0,.2,1), box-shadow 0.2s;
      }
      button:hover:not(:disabled) {
        transform: translateY(-1px) scale(1.02);
        box-shadow: 0 4px 20px rgba(96,165,250,0.4);
      }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
      .status-row { display: flex; align-items: center; gap: 0.45rem; min-height: 1.4rem; margin-top: 0.6rem; }
      #status { font-weight: 600; font-size: 0.85rem; color: var(--accent); }
      @media (max-width: 600px) { main { padding: 1.5rem 1rem 2.5rem; } }
    </style>
  </head>
  <body>
    <main>
      <h1>City Guide</h1>
      <p class="subtitle">Plan a city break, compare neighborhoods, or sketch a practical travel brief with time and weather context when it helps.</p>
      <div class="chips">
        <span class="chip">Gemini</span>
        <span class="chip">Travel planning</span>
        <span class="chip">Time and weather cues</span>
      </div>
      <section class="glass">
        <div id="thread">
          <div class="typing-indicator" id="typing"><span></span><span></span><span></span></div>
        </div>
        <textarea id="message">Plan a founder-friendly 2-day Tokyo itinerary with coffee spots, neighborhoods to stay in, and the best time windows for meetings.</textarea>
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

      function render(role, text) {
        const node = document.createElement("div");
        node.className = "bubble " + role;
        node.textContent = text;
        thread.insertBefore(node, typing);
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
          render("assistant", payload.reply);
          history.push({ role: "assistant", content: payload.reply });
          status.textContent = "Ready.";
        } catch (error) {
          typing.classList.remove("active");
          if (error instanceof DOMException && error.name === "AbortError") {
            status.textContent = "Gemini took too long to respond. Try again.";
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


def render_history(history: list[Message], latest: str) -> str:
    turns = history[-8:]
    lines = ["Conversation so far:"]
    for turn in turns:
        role = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{role}: {turn.content.strip()}")
    lines.append(f"User: {latest}")
    return "\n".join(lines)


async def run_agent(message: str, history: list[Message]) -> str:
    session_service = InMemorySessionService()
    session_id = uuid.uuid4().hex
    await session_service.create_session(app_name=APP_NAME, user_id="web-user", session_id=session_id)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
    prompt = render_history(history, message)
    async for event in runner.run_async(
        user_id="web-user",
        session_id=session_id,
        new_message=genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)],
        ),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            return event.content.parts[0].text or ""
    raise RuntimeError("The ADK runner did not return a final response.")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.get("/health")
async def health() -> dict[str, str]:
    return {"ok": "true", "runtime": "google-adk", "model": MODEL_NAME}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")
    try:
        reply = await asyncio.wait_for(
            run_agent(message, request.history),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Gemini took too long to respond. Try again in a moment.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=friendly_provider_error(exc)) from exc
    return {"reply": reply}
