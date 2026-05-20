from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from integrations.stripe import fetch_revenue_kpis
from lib.dashboard import render_dashboard
from lib.secrets import mock_enabled

app = FastAPI(title="Stripe Revenue Dashboard")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "ok": "true",
        "slug": "recipe-24-stripe-revenue-dashboard",
        "stripe_mock": str(mock_enabled("STRIPE_MOCK")).lower(),
    }


def _load_kpis():
    try:
        return fetch_revenue_kpis()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(render_dashboard(_load_kpis()))


@app.get("/api/kpis")
def kpis_json() -> JSONResponse:
    k = _load_kpis()
    return JSONResponse(
        {
            "mrr": k.mrr,
            "arr": k.arr,
            "active_subs": k.active_subs,
            "churn_rate_pct": k.churn_rate_pct,
            "trial_conversion_pct": k.trial_conversion_pct,
            "as_of": k.as_of,
        }
    )
