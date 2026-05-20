"""Investor CRM updater — email signal webhook, LLM extract, JSON CRM upsert."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from lib.config import SAMPLE_EMAIL_SIGNAL, crm_path
from lib.llm import LLMClient
from lib.store import CrmStore

EXTRACT_SYSTEM = """Extract investor CRM fields from an email signal.
Return JSON with keys: name, email, company, title, stage, sentiment, summary.
stage is one of: intro, interested, due_diligence, passed, invested.
sentiment is one of: positive, neutral, negative."""


@dataclass
class CrmResult:
    email: str
    record: dict[str, Any]
    created: bool
    dry_run: bool


@dataclass
class RunResult:
    fetched: int
    new: int
    kept: int
    digest: str
    mail_sent: bool
    dry_run: bool


def process_email_signal(
    signal: dict[str, Any],
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> CrmResult:
    from_email = str(signal.get("from_email") or signal.get("email") or "").lower().strip()
    from_name = str(signal.get("from_name") or signal.get("name") or "")
    subject = str(signal.get("subject") or "")
    preview = str(signal.get("body_preview") or signal.get("snippet") or "")

    if dry_run:
        record = {
            "name": from_name or "Unknown",
            "email": from_email,
            "company": _guess_company(from_email),
            "stage": "intro",
            "sentiment": "neutral",
            "summary": f"Dry run — LLM skipped. Subject: {subject}",
            "last_activity": _now(),
        }
        return CrmResult(email=from_email, record=record, created=True, dry_run=True)

    client = llm or LLMClient(client=http)
    prompt = f"From: {from_name} <{from_email}>\nSubject: {subject}\nPreview: {preview[:500]}"
    extracted = client.complete_json(EXTRACT_SYSTEM, prompt)
    record = {
        "name": str(extracted.get("name") or from_name),
        "email": str(extracted.get("email") or from_email),
        "company": str(extracted.get("company") or _guess_company(from_email)),
        "title": str(extracted.get("title") or ""),
        "stage": str(extracted.get("stage") or "intro"),
        "sentiment": str(extracted.get("sentiment") or "neutral"),
        "summary": str(extracted.get("summary") or preview[:200]),
        "last_activity": _now(),
    }

    store = CrmStore(crm_path())
    created = store.get(from_email) is None
    saved = store.upsert(from_email, record)
    return CrmResult(email=from_email, record=saved, created=created, dry_run=False)


def run_crm_update(
    signal: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> RunResult:
    payload = signal or SAMPLE_EMAIL_SIGNAL
    result = process_email_signal(payload, dry_run=dry_run, llm=llm, http=http)
    digest = (
        f"CRM {'preview' if result.dry_run else 'updated'}: {result.email}\n"
        f"Stage: {result.record.get('stage')} | Sentiment: {result.record.get('sentiment')}\n"
        f"{result.record.get('summary')}"
    )
    return RunResult(
        fetched=1,
        new=1 if result.created else 0,
        kept=1,
        digest=digest,
        mail_sent=False,
        dry_run=result.dry_run,
    )


def _guess_company(email: str) -> str:
    if "@" not in email:
        return ""
    domain = email.split("@", 1)[1]
    return domain.split(".")[0].title()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
