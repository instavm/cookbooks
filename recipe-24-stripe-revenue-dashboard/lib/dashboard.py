from __future__ import annotations

from integrations.stripe import RevenueKPIs
from lib.ui import ops_dashboard


def _fmt_pct(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "N/A"


def render_dashboard(kpis: RevenueKPIs) -> str:
    return ops_dashboard(
        title="Revenue Dashboard",
        subtitle=f"Stripe KPIs as of {kpis.as_of}",
        metrics=[
            ("MRR", f"${kpis.mrr:,.0f}", False),
            ("ARR", f"${kpis.arr:,.0f}", False),
            ("Active subs", str(kpis.active_subs), False),
            ("Churn rate", _fmt_pct(kpis.churn_rate_pct), True),
            ("Trial conversion", _fmt_pct(kpis.trial_conversion_pct), False),
        ],
        slug="recipe-24-stripe-revenue-dashboard",
    )
