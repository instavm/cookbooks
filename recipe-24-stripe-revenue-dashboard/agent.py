"""Stripe revenue dashboard — KPI loader for tests and CLI."""

from __future__ import annotations

from integrations.stripe import RevenueKPIs, fetch_revenue_kpis


def load_kpis() -> RevenueKPIs:
    return fetch_revenue_kpis()
