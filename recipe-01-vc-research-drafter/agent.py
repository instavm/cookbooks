"""VC research drafter — Exa search, dedup, warm-intro drafts, Mailtrap."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from integrations.exa import VCResult, search_vcs
from lib.config import (
    COMPANY_BLURB,
    DRAFT_TO,
    MAX_DRAFTS_PER_RUN,
    MAX_VCS,
    VC_THESIS,
    contacted_path,
)
from lib.llm import LLMClient
from lib.mail import send_email
from lib.store import JsonStore

DRAFT_SYSTEM = """You draft warm intro emails from a founder to a VC.
Return JSON: {"subject": "...", "body": "..."}
Subject line first in JSON. Body is 3-4 sentences, specific, no fluff."""


@dataclass
class RunResult:
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


def run_draft(*, dry_run: bool = False, llm: LLMClient | None = None, http: httpx.Client | None = None) -> RunResult:
    store = JsonStore(contacted_path())
    vcs = search_vcs(VC_THESIS, limit=MAX_VCS, client=http)
    new_vcs = [v for v in vcs if not store.seen(v.url)]

    if not new_vcs:
        return RunResult(
            fetched=len(vcs),
            new=0,
            kept=0,
            digest="No new VCs to contact.",
            mail_sent=False,
            dry_run=dry_run,
        )

    if dry_run:
        digest = _format_digest(new_vcs[:MAX_DRAFTS_PER_RUN], note="Dry run — LLM skipped.")
        return RunResult(
            fetched=len(vcs),
            new=len(new_vcs),
            kept=min(MAX_DRAFTS_PER_RUN, len(new_vcs)),
            digest=digest,
            mail_sent=False,
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    drafted: list[VCResult] = []
    email_bodies: list[str] = []

    for vc in new_vcs[:MAX_DRAFTS_PER_RUN]:
        prompt = (
            f"VC: {vc.title}\nURL: {vc.url}\nContext: {vc.snippet}\n"
            f"Founder company: {COMPANY_BLURB}"
        )
        draft = client.complete_json(DRAFT_SYSTEM, prompt)
        subject = str(draft.get("subject") or f"Intro — {vc.title}")
        body = str(draft.get("body") or "")
        email_bodies.append(f"To: {vc.title}\nSubject: {subject}\n\n{body}")
        drafted.append(vc)

    digest = _format_digest(drafted, note="\n\n".join(email_bodies))
    store.mark_many(v.url for v in new_vcs)
    store.flush()

    mail = send_email(to=DRAFT_TO, subject="VC Warm Intro Drafts", body=digest, dry_run=False)
    return RunResult(
        fetched=len(vcs),
        new=len(new_vcs),
        kept=len(drafted),
        digest=digest,
        mail_sent=mail.sent,
        dry_run=False,
    )


def _format_digest(vcs: list[VCResult], *, note: str) -> str:
    lines = [note, "", "VCs:"]
    for v in vcs:
        lines.append(f"- {v.title}\n  {v.url}\n  {v.snippet[:120]}")
    return "\n".join(lines)
