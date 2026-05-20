import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STRIPE_MOCK", "1")
    return TestClient(app)


def test_landing_page_is_html_not_json(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "application/json" not in resp.text[:120]


def test_landing_has_readable_content(client):
    resp = client.get("/")
    assert any(
        marker in resp.text
        for marker in ("InstaVM Cookbook", "Revenue Dashboard", "Screen replay", "Computer-use")
    )
