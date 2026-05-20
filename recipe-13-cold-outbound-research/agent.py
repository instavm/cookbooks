"""Cold outbound — Exa research, LLM email, Mailtrap send."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from integrations.exa import ExaHit, research_company
from lib.config import DIGEST_TO, emailed_path
from lib.llm import LLMClient
from lib.mail import send_email
from lib.store import JsonStore

EMAIL_SYSTEM = """You write concise, personalized cold outbound emails for B2B SaaS.
Return JSON only: {"subject": "...", "body": "plain text email body"}
Reference one specific research hook from the snippets. Keep under 120 words."""


@dataclass
class ProspectResult:
    company: str
    email: str
    research_hits: int
    subject: str
    body: str
    mail_sent: bool
    skipped: bool
    dry_run: bool


def research_and_email(
    *,
    name: str,
    email: str,
    company: str,
    domain: str = "",
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> ProspectResult:
    store = JsonStore(emailed_path())
    if store.seen(email):
        return ProspectResult(
            company=company,
            email=email,
            research_hits=0,
            subject="",
            body="",
            mail_sent=False,
            skipped=True,
            dry_run=dry_run,
        )

    hits = research_company(company, domain=domain, client=http)
    if dry_run:
        subject = f"Quick thought on {company}"
        body = f"Hi {name},\n\nDry run — LLM skipped. Found {len(hits)} research hits."
        return ProspectResult(
            company=company,
            email=email,
            research_hits=len(hits),
            subject=subject,
            body=body,
            mail_sent=False,
            skipped=False,
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    payload = {
        "prospect": {"name": name, "email": email, "company": company, "domain": domain},
        "research": [_hit_dict(h) for h in hits],
    }
    draft: dict[str, Any] = client.complete_json(EMAIL_SYSTEM, str(payload))
    subject = str(draft.get("subject") or f"Quick thought on {company}")
    body = str(draft.get("body") or "")

    mail = send_email(to=email or DIGEST_TO, subject=subject, body=body, dry_run=False)
    store.mark_many([email])
    store.flush()

    return ProspectResult(
        company=company,
        email=email,
        research_hits=len(hits),
        subject=subject,
        body=body,
        mail_sent=mail.sent,
        skipped=False,
        dry_run=False,
    )


def _hit_dict(hit: ExaHit) -> dict[str, str]:
    return {"title": hit.title, "url": hit.url, "snippet": hit.snippet}
