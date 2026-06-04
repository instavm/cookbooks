"""Post-meeting follow-up — transcript webhook, LLM email draft, save to volume."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from lib.config import SAMPLE_TRANSCRIPT, followups_dir
from lib.llm import LLMClient

FOLLOWUP_SYSTEM = """Analyze a meeting transcript and draft a follow-up email.
Return JSON: {"subject": "...", "body": "...", "action_items": ["..."]}
Body should be warm, concise, and reference specific next steps."""


@dataclass
class FollowupResult:
    subject: str
    body: str
    action_items: list[str]
    saved_path: str | None
    dry_run: bool


@dataclass
class RunResult:
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


def process_transcript(
    payload: dict[str, Any],
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> FollowupResult:
    title = str(payload.get("title") or "Meeting follow-up")
    attendee = str(payload.get("attendee_name") or "there")
    transcript = str(payload.get("transcript") or "")

    if dry_run:
        subject = f"Follow-up: {title}"
        body = (
            f"Hi {attendee},\n\n"
            "Dry run — LLM skipped.\n\n"
            f"Transcript preview: {transcript[:200]}"
        )
        return FollowupResult(
            subject=subject,
            body=body,
            action_items=["Review transcript manually"],
            saved_path=None,
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    prompt = f"Meeting: {title}\nAttendee: {attendee}\n\nTranscript:\n{transcript[:8000]}"
    draft = client.complete_json(FOLLOWUP_SYSTEM, prompt)
    subject = str(draft.get("subject") or f"Follow-up: {title}")
    body = str(draft.get("body") or "")
    action_items = [str(item) for item in (draft.get("action_items") or [])]
    saved = _save_followup(payload, subject, body, action_items)
    return FollowupResult(
        subject=subject,
        body=body,
        action_items=action_items,
        saved_path=str(saved),
        dry_run=False,
    )


def run_followup(
    payload: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> RunResult:
    data = payload or SAMPLE_TRANSCRIPT
    result = process_transcript(data, dry_run=dry_run, llm=llm, http=http)
    digest = f"Subject: {result.subject}\n\n{result.body}"
    return RunResult(
        fetched=1,
        new=1,
        kept=1,
        digest=digest,
        mail_sent=False,
        dry_run=result.dry_run,
    )


def _save_followup(payload: dict[str, Any], subject: str, body: str, action_items: list[str]) -> Path:
    out_dir = followups_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    email = str(payload.get("attendee_email") or "unknown").replace("@", "_")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{email}_{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "title": payload.get("title"),
                "attendee_email": payload.get("attendee_email"),
                "subject": subject,
                "body": body,
                "action_items": action_items,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
