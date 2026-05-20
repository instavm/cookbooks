import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] == "true"


def test_dashboard_html(client, monkeypatch):
    monkeypatch.setenv("STRIPE_MOCK", "1")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Revenue Dashboard" in resp.text
    assert "MRR" in resp.text


def test_kpis_json(client, monkeypatch):
    monkeypatch.setenv("STRIPE_MOCK", "1")
    resp = client.get("/api/kpis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mrr"] > 0
    assert body["active_subs"] > 0
