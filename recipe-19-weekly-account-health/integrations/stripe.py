from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from lib.secrets import mock_enabled, vault_credential

STRIPE_API = "https://api.stripe.com/v1/subscriptions"


@dataclass
class AccountMetrics:
    mrr: float
    churn_count: int
    active_subs: int
    week: str


def _mock_metrics() -> AccountMetrics:
    return AccountMetrics(mrr=48250.0, churn_count=3, active_subs=128, week=str(date.today()))


def fetch_account_metrics(*, client: httpx.Client | None = None) -> AccountMetrics:
    if mock_enabled("STRIPE_MOCK"):
        return _mock_metrics()

    http = client or httpx.Client(timeout=30.0)
    key = vault_credential("STRIPE_KEY")
    resp = http.get(
        STRIPE_API,
        params={"status": "active", "limit": 100},
        headers={"Authorization": f"Bearer {key}"},
    )
    resp.raise_for_status()
    data = resp.json()
    mrr_cents = 0
    active = 0
    for sub in data.get("data", []):
        items = sub.get("items", {}).get("data", [])
        if not items:
            continue
        price = items[0].get("price", {})
        if price.get("recurring", {}).get("interval") == "month":
            mrr_cents += int(price.get("unit_amount") or 0) * int(items[0].get("quantity") or 1)
            active += 1
    return AccountMetrics(
        mrr=mrr_cents / 100.0,
        churn_count=0,
        active_subs=active,
        week=str(date.today()),
    )


def metrics_to_dict(metrics: AccountMetrics) -> dict[str, Any]:
    return {
        "mrr": metrics.mrr,
        "churn_count": metrics.churn_count,
        "active_subs": metrics.active_subs,
        "week": metrics.week,
    }
