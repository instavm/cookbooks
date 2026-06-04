import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_fixtures(client):
    resp = client.get("/fixtures")
    assert resp.status_code == 200
    assert len(resp.json()["accounts"]) == 3


def test_scan_dry_run(client):
    resp = client.post("/scan?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["accounts_scored"] == 3
