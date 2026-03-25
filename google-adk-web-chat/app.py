from __future__ import annotations

import datetime as dt
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

MODEL_NAME = os.environ.get("GOOGLE_MODEL", "gemini-2.0-flash")
APP_NAME = "instavm-google-adk-web-chat"


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

app = FastAPI(title="Google ADK Web Chat")


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
    <title>Google ADK Web Chat</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #eff5fb;
        --panel: #ffffff;
        --ink: #102136;
        --muted: #5f6e80;
        --accent: #1c6ce5;
        --accent-soft: #d9e8ff;
        --border: #d7e0ec;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Soehne", "Segoe UI", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, #dce9ff, transparent 24rem),
          linear-gradient(180deg, #fbfdff, var(--bg));
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
        box-shadow: 0 16px 36px rgba(16, 33, 54, 0.06);
      }
      #thread {
        min-height: 360px;
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
      .user { background: #102136; color: #fff; justify-self: end; max-width: 80%; }
      .assistant { background: #f5f8fd; color: var(--ink); max-width: 100%; }
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
      <h1>Google ADK Web Chat</h1>
      <p>Ask this starter to plan a city break, compare neighborhoods, or sketch a lightweight travel brief. It uses the Google ADK runner path with small helper tools for time and weather context.</p>
      <div class="chips">
        <span class="chip">Google ADK</span>
        <span class="chip">Gemini-backed</span>
        <span class="chip">FastAPI share-ready</span>
      </div>
      <section class="panel">
        <div id="thread"></div>
        <textarea id="message">Plan a founder-friendly 2-day Tokyo itinerary with coffee spots, neighborhoods to stay in, and the best time windows for meetings.</textarea>
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
        thread.scrollTop = thread.scrollHeight;
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
          render("assistant", payload.reply);
          history.push({ role: "assistant", content: payload.reply });
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
        reply = await run_agent(message, request.history)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"ADK chat failed: {exc}") from exc
    return {"reply": reply}
