"""Weekly account health — Stripe metrics, week-over-week diff, LLM narrative, Slack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from integrations.slack import post_digest
from integrations.stripe import fetch_account_metrics, metrics_to_dict
from lib.config import history_path
from lib.history import append_entry, load_history
from lib.llm import LLMClient

SUMMARY_SYSTEM = """You write concise customer-success health summaries for Slack.
Return JSON: {"summary": "2-3 sentences", "action": "one recommended action"}
Be direct about MRR movement and churn risk."""


@dataclass
class RunResult:
    mrr: float
    delta_mrr: float
    churn_count: int
    digest: str
    slack_sent: bool
    dry_run: bool


def run_health_digest(*, dry_run: bool = False, llm: LLMClient | None = None, http: httpx.Client | None = None) -> RunResult:
    metrics = fetch_account_metrics(client=http)
    current = metrics_to_dict(metrics)
    history = load_history(history_path())
    prev = history[-1] if history else current
    delta_mrr = float(current["mrr"]) - float(prev.get("mrr", current["mrr"]))

    header = (
        f"*Account Health — {current['week']}*\n"
        f"MRR: ${current['mrr']:,.0f} ({delta_mrr:+,.0f} WoW) · "
        f"Churned: {current['churn_count']} · Active subs: {current['active_subs']}"
    )

    if dry_run:
        digest = f"{header}\n\nDry run — LLM and Slack skipped."
        return RunResult(
            mrr=current["mrr"],
            delta_mrr=delta_mrr,
            churn_count=current["churn_count"],
            digest=digest,
            slack_sent=False,
            dry_run=True,
        )

    client = llm or LLMClient(client=http)
    narrative: dict[str, Any] = client.complete_json(
        SUMMARY_SYSTEM,
        f"MRR ${current['mrr']:,.0f}, delta {delta_mrr:+,.0f}, churn {current['churn_count']}",
    )
    summary = str(narrative.get("summary") or "")
    action = str(narrative.get("action") or "")
    digest = f"{header}\n\n{summary}\n\n*Action:* {action}"

    append_entry(history_path(), current)
    slack = post_digest(text=digest, dry_run=False, client=http)

    return RunResult(
        mrr=current["mrr"],
        delta_mrr=delta_mrr,
        churn_count=current["churn_count"],
        digest=digest,
        slack_sent=slack.sent,
        dry_run=False,
    )
