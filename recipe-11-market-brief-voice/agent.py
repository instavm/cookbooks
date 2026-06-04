"""Market brief voice — Linkup news, LLM script, Cartesia TTS stub, audio on volume."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx

from integrations.cartesia import synthesize
from integrations.linkup import NewsStory, fetch_news
from lib.config import audio_dir, heard_path, latest_audio_path
from lib.llm import LLMClient
from lib.store import JsonStore

SCRIPT_SYSTEM = """Write a 60-second spoken market brief for a senior tech founder.
Conversational, no jargon, three topics max, end with one forward-looking sentence.
Return JSON: {"script": "pure prose for TTS, no headers or bullets"}"""


@dataclass
class BriefResult:
    stories: int
    new_stories: int
    script: str
    audio_bytes: int
    tts_stub: bool
    skipped: bool
    dry_run: bool


def run_brief(
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> BriefResult:
    stories = fetch_news(client=http)
    store = JsonStore(heard_path())
    new_stories = [s for s in stories if not store.seen(s.id)]

    if not new_stories:
        return BriefResult(
            stories=len(stories),
            new_stories=0,
            script="",
            audio_bytes=0,
            tts_stub=True,
            skipped=True,
            dry_run=dry_run,
        )

    snippets = "\n\n".join(f"- {s.name}: {s.content[:300]}" for s in new_stories)

    if dry_run:
        script = f"Good morning. Today is {date.today().isoformat()}. Here is your market brief. {snippets[:200]}"
        tts = synthesize(script, client=http)
    else:
        client = llm or LLMClient(client=http)
        parsed = client.complete_json(SCRIPT_SYSTEM, f"Today is {date.today().isoformat()}.\n\n{snippets}")
        script = str(parsed.get("script") or "")
        tts = synthesize(script, client=http)

    out_dir = audio_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_audio_path().write_bytes(tts.audio)
    dated = out_dir / f"brief_{date.today().isoformat()}.mp3"
    dated.write_bytes(tts.audio)

    if not dry_run:
        store.mark_many(s.id for s in new_stories)
        store.flush()

    return BriefResult(
        stories=len(stories),
        new_stories=len(new_stories),
        script=script,
        audio_bytes=len(tts.audio),
        tts_stub=tts.stub,
        skipped=False,
        dry_run=dry_run,
    )


def read_latest_audio() -> bytes | None:
    path = latest_audio_path()
    if path.exists():
        return path.read_bytes()
    return None
