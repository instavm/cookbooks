"""Churn risk warning — Stripe + Intercom fixtures, LLM score, Slack/Mailtrap alert."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from lib.config import ALERT_TO, intercom_fixture, stripe_fixture
from lib.llm import LLMClient
from lib.mail import send_email
from lib.slack import post_slack_message

RISK_SYSTEM = """You score churn risk for B2B SaaS accounts.
Return JSON only:
{
  "accounts": [
    {
      "customer_id": "...",
      "customer_name": "...",
      "risk_score": 0-100,
      "risk_level": "low|medium|high",
      "signals": ["..."],
      "recommended_action": "one sentence"
    }
  ],
  "summary": "one paragraph for CS leadership"
}
Flag high risk when billing is past_due, cancel_at_period_end, or sentiment is negative."""


@dataclass
class ScanResult:
    accounts_scored: int
    high_risk: int
    assessment: dict[str, Any]
    slack_sent: bool
    mail_sent: bool
    dry_run: bool


def load_fixtures(
    *,
    stripe_path: Path | None = None,
    intercom_path: Path | None = None,
) -> list[dict[str, Any]]:
    subs = json.loads((stripe_path or stripe_fixture()).read_text(encoding="utf-8"))
    sentiment = json.loads((intercom_path or intercom_fixture()).read_text(encoding="utf-8"))
    by_id = {row["customer_id"]: row for row in sentiment}
    merged: list[dict[str, Any]] = []
    for sub in subs:
        row = dict(sub)
        row["intercom"] = by_id.get(sub["customer_id"], {})
        merged.append(row)
    return merged


def scan_churn_risk(
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> ScanResult:
    accounts = load_fixtures()
    if dry_run:
        assessment = {
            "accounts": [
                {
                    "customer_id": a["customer_id"],
                    "customer_name": a["customer_name"],
                    "risk_score": 80 if a.get("status") == "past_due" else 20,
                    "risk_level": "high" if a.get("status") == "past_due" else "low",
                    "signals": ["dry run"],
                    "recommended_action": "Review manually",
                }
                for a in accounts
            ],
            "summary": "Dry run — LLM skipped.",
        }
        high = sum(1 for x in assessment["accounts"] if x["risk_level"] == "high")
        return ScanResult(
            accounts_scored=len(accounts),
            high_risk=high,
            assessment=assessment,
            slack_sent=False,
            mail_sent=False,
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    assessment = client.complete_json(RISK_SYSTEM, json.dumps(accounts, indent=2))
    scored = assessment.get("accounts") or []
    high = sum(1 for row in scored if str(row.get("risk_level", "")).lower() == "high")

    summary = str(assessment.get("summary") or "")
    alert_body = _format_alert(scored, summary=summary)
    slack = post_slack_message(alert_body, client=http)
    mail = send_email(
        to=ALERT_TO,
        subject=f"Churn risk alert — {high} high-risk accounts",
        body=alert_body,
        dry_run=False,
    )

    return ScanResult(
        accounts_scored=len(scored) or len(accounts),
        high_risk=high,
        assessment=assessment,
        slack_sent=slack.sent,
        mail_sent=mail.sent,
        dry_run=False,
    )


def _format_alert(scored: list[dict[str, Any]], *, summary: str) -> str:
    lines = [summary, ""]
    for row in scored:
        if str(row.get("risk_level", "")).lower() != "high":
            continue
        lines.append(
            f"- {row.get('customer_name')} ({row.get('customer_id')}): "
            f"score={row.get('risk_score')} — {row.get('recommended_action')}"
        )
    if len(lines) <= 2:
        lines.append("No high-risk accounts this run.")
    return "\n".join(lines)
