from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import httpx

from lib.secrets import mock_enabled, vault_credential

STRIPE_API = "https://api.stripe.com/v1"


@dataclass
class StripeMetrics:
    mrr_usd: float
    new_customers_this_month: int
    churned_this_month: int
    month: str

    def to_dict(self) -> dict:
        return asdict(self)


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _mock_metrics() -> StripeMetrics:
    return StripeMetrics(
        mrr_usd=12_500.0,
        new_customers_this_month=14,
        churned_this_month=2,
        month=_current_month(),
    )


def fetch_stripe_metrics(*, client: httpx.Client | None = None) -> StripeMetrics:
    if mock_enabled("STRIPE_TEST_MODE") or mock_enabled("STRIPE_MOCK"):
        return _mock_metrics()

    key = vault_credential("STRIPE_KEY")
    http = client or httpx.Client(timeout=30.0)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    headers = {"Authorization": f"Bearer {key}"}

    subs_resp = http.get(
        f"{STRIPE_API}/subscriptions",
        headers=headers,
        params={"status": "active", "limit": 100},
    )
    subs_resp.raise_for_status()
    subs = subs_resp.json().get("data", [])

    mrr = 0.0
    for sub in subs:
        for item in sub.get("items", {}).get("data", []):
            price = item.get("price") or {}
            amount = float(price.get("unit_amount") or 0) / 100
            qty = int(item.get("quantity") or 1)
            interval = (price.get("recurring") or {}).get("interval", "month")
            monthly = amount * qty / (12 if interval == "year" else 1)
            mrr += monthly

    cust_resp = http.get(
        f"{STRIPE_API}/customers",
        headers=headers,
        params={"created[gte]": int(month_start.timestamp()), "limit": 100},
    )
    cust_resp.raise_for_status()
    new_customers = len(cust_resp.json().get("data", []))

    churn_resp = http.get(
        f"{STRIPE_API}/subscriptions",
        headers=headers,
        params={
            "status": "canceled",
            "canceled_at[gte]": int(month_start.timestamp()),
            "limit": 100,
        },
    )
    churn_resp.raise_for_status()
    churned = len(churn_resp.json().get("data", []))

    return StripeMetrics(
        mrr_usd=round(mrr, 2),
        new_customers_this_month=new_customers,
        churned_this_month=churned,
        month=month_start.strftime("%Y-%m"),
    )
