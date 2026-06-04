"""Investor update assembler — Stripe + GitHub metrics, KPI history, LLM draft."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from integrations.github import GitHubMetrics, fetch_github_metrics
from integrations.stripe import StripeMetrics, fetch_stripe_metrics
from lib.config import kpi_history_path, updates_dir
from lib.llm import LLMClient

ASSEMBLE_SYSTEM = """You write concise monthly investor update emails for startup founders.
Return JSON: {"update": "markdown body", "headline": "one line summary"}
Sections: Headline metrics, Progress highlights, What's next, Ask (if any).
Do not fabricate team names or product features not mentioned in the data."""


@dataclass
class AssembleResult:
    month: str
    mrr_usd: float
    commits: int
    prs_merged: int
    update: str
    headline: str
    history_months: int
    dry_run: bool


def load_kpi_history() -> list[dict[str, Any]]:
    path = kpi_history_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def save_kpi_snapshot(stripe: StripeMetrics, github: GitHubMetrics) -> None:
    path = kpi_history_path()
    history = load_kpi_history()
    history.append(
        {
            "stripe": stripe.to_dict(),
            "github": github.to_dict(),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history[-13:], indent=2), encoding="utf-8")


def run_assemble(
    *,
    dry_run: bool = False,
    llm: LLMClient | None = None,
    http: httpx.Client | None = None,
) -> AssembleResult:
    stripe = fetch_stripe_metrics(client=http)
    github = fetch_github_metrics(client=http)
    history = load_kpi_history()

    if dry_run:
        update = _dry_run_text(stripe, github, history)
        return AssembleResult(
            month=stripe.month,
            mrr_usd=stripe.mrr_usd,
            commits=github.commits_this_month,
            prs_merged=github.prs_merged_this_month,
            update=update,
            headline=f"MRR ${stripe.mrr_usd:,.0f} — dry run",
            history_months=len(history),
            dry_run=True,
        )

    mrr_trend = [h["stripe"]["mrr_usd"] for h in history[-6:]] + [stripe.mrr_usd]
    trend_str = " → ".join(f"${m:,.0f}" for m in mrr_trend)
    user = (
        f"Current MRR: ${stripe.mrr_usd:,.2f}. 6-month trend: {trend_str}. "
        f"New customers: {stripe.new_customers_this_month}. "
        f"Churn: {stripe.churned_this_month}. "
        f"Commits: {github.commits_this_month}. PRs merged: {github.prs_merged_this_month}."
    )

    client = llm or LLMClient(client=http)
    parsed: dict[str, Any] = client.complete_json(ASSEMBLE_SYSTEM, user)
    update = str(parsed.get("update") or "")
    headline = str(parsed.get("headline") or f"Investor update {stripe.month}")

    out_dir = updates_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stripe.month}-investor-update.md").write_text(update, encoding="utf-8")
    save_kpi_snapshot(stripe, github)

    return AssembleResult(
        month=stripe.month,
        mrr_usd=stripe.mrr_usd,
        commits=github.commits_this_month,
        prs_merged=github.prs_merged_this_month,
        update=update,
        headline=headline,
        history_months=len(history) + 1,
        dry_run=False,
    )


def _dry_run_text(stripe: StripeMetrics, github: GitHubMetrics, history: list[dict]) -> str:
    return (
        f"# Investor Update {stripe.month} (dry run)\n\n"
        f"MRR: ${stripe.mrr_usd:,.2f} | New customers: {stripe.new_customers_this_month} | "
        f"Churn: {stripe.churned_this_month}\n"
        f"Engineering: {github.commits_this_month} commits, {github.prs_merged_this_month} PRs merged\n"
        f"History entries: {len(history)}"
    )
