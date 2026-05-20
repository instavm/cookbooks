"""Pre-meeting briefing — Cal.com webhook, Exa research, markdown briefing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from integrations.exa import ResearchHit, research_attendee
from lib.config import briefings_dir
from lib.llm import LLMClient

BRIEFING_SYSTEM = """Write a one-page pre-meeting briefing in markdown for a founder.
Cover: who they are, recent news, likely agenda, 3 talking points, and risks.
Be concise and actionable."""


@dataclass
class BriefingResult:
    attendee_name: str
    attendee_email: str
    company: str
    briefing: str
    research_count: int
    dry_run: bool
    saved_path: str | None = None


@dataclass
class RunResult:
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


def parse_cal_event(event: dict[str, Any]) -> dict[str, str]:
    attendees = event.get("attendees") or []
    first = attendees[0] if attendees else {}
    return {
        "attendee_name": str(first.get("name") or "Unknown"),
        "attendee_email": str(first.get("email") or ""),
        "company": str(first.get("organization") or first.get("company") or ""),
        "start_time": str(event.get("startTime") or ""),
        "title": str(event.get("title") or "Meeting"),
    }


def build_briefing(
    event: dict[str, Any],
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> BriefingResult:
    meeting = parse_cal_event(event)
    research = research_attendee(
        meeting["attendee_name"],
        meeting["company"],
        meeting["attendee_email"],
        client=http,
    )

    if dry_run:
        briefing = _dry_run_briefing(meeting, research)
        return BriefingResult(
            attendee_name=meeting["attendee_name"],
            attendee_email=meeting["attendee_email"],
            company=meeting["company"],
            briefing=briefing,
            research_count=len(research),
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    context = "\n".join(f"- {r.title}: {r.snippet}" for r in research)
    prompt = (
        f"Meeting: {meeting['title']} with {meeting['attendee_name']} "
        f"from {meeting['company']} at {meeting['start_time']}.\n"
        f"Research:\n{context}"
    )
    briefing = client.complete(BRIEFING_SYSTEM, prompt).text
    saved = _save_briefing(meeting["attendee_email"], briefing)
    return BriefingResult(
        attendee_name=meeting["attendee_name"],
        attendee_email=meeting["attendee_email"],
        company=meeting["company"],
        briefing=briefing,
        research_count=len(research),
        dry_run=False,
        saved_path=str(saved),
    )


def run_briefing(
    event: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> RunResult:
    from lib.config import SAMPLE_ATTENDEE

    payload = event or SAMPLE_ATTENDEE
    result = build_briefing(payload, dry_run=dry_run, llm=llm, http=http)
    return RunResult(
        fetched=result.research_count,
        new=1,
        kept=1,
        digest=result.briefing,
        mail_sent=False,
        dry_run=result.dry_run,
    )


def _dry_run_briefing(meeting: dict[str, str], research: list[ResearchHit]) -> str:
    lines = [
        f"# Pre-meeting briefing: {meeting['attendee_name']}",
        "",
        f"**Company:** {meeting['company']}",
        f"**When:** {meeting['start_time']}",
        "",
        "## Research hits (dry run — LLM skipped)",
    ]
    for hit in research[:5]:
        lines.append(f"- [{hit.title}]({hit.url})")
    return "\n".join(lines)


def _save_briefing(email: str, briefing: str) -> Path:
    out_dir = briefings_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = email.replace("@", "_") or "unknown"
    path = out_dir / f"{slug}.md"
    path.write_text(briefing, encoding="utf-8")
    return path
