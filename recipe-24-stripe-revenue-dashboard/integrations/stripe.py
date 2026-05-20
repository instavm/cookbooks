from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx

from lib.secrets import mock_enabled, vault_credential

STRIPE_SUBS = "https://api.stripe.com/v1/subscriptions"


@dataclass
class RevenueKPIs:
    mrr: float
    arr: float
    active_subs: int
    churn_rate_pct: float | None
    trial_conversion_pct: float | None
    as_of: str


def _mock_kpis() -> RevenueKPIs:
    mrr = 48250.0
    return RevenueKPIs(
        mrr=mrr,
        arr=mrr * 12,
        active_subs=128,
        churn_rate_pct=2.4,
        trial_conversion_pct=18.5,
        as_of=str(date.today()),
    )


def fetch_revenue_kpis(*, client: httpx.Client | None = None) -> RevenueKPIs:
    if mock_enabled("STRIPE_MOCK"):
        return _mock_kpis()

    http = client or httpx.Client(timeout=30.0)
    key = vault_credential("STRIPE_KEY")
    headers = {"Authorization": f"Bearer {key}"}
    subs_resp = http.get(STRIPE_SUBS, params={"status": "active", "limit": 100}, headers=headers)
    subs_resp.raise_for_status()
    mrr_cents = 0
    active = 0
    for sub in subs_resp.json().get("data", []):
        items = sub.get("items", {}).get("data", [])
        if not items:
            continue
        price = items[0].get("price", {})
        if price.get("recurring", {}).get("interval") == "month":
            mrr_cents += int(price.get("unit_amount") or 0) * int(items[0].get("quantity") or 1)
            active += 1
    mrr = mrr_cents / 100.0
    return RevenueKPIs(
        mrr=mrr,
        arr=mrr * 12,
        active_subs=active,
        churn_rate_pct=None,
        trial_conversion_pct=None,
        as_of=str(date.today()),
    )
