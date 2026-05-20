from integrations.stripe import fetch_revenue_kpis
from lib.dashboard import render_dashboard


def test_fetch_kpis_mock(monkeypatch):
    monkeypatch.setenv("STRIPE_MOCK", "1")
    kpis = fetch_revenue_kpis()
    assert kpis.mrr > 0
    assert kpis.arr == kpis.mrr * 12


def test_render_dashboard(monkeypatch):
    monkeypatch.setenv("STRIPE_MOCK", "1")
    html = render_dashboard(fetch_revenue_kpis())
    assert "Revenue Dashboard" in html
    assert "motion" not in html
