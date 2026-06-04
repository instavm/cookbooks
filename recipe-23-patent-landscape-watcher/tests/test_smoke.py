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


def test_run_dry_run(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EXA_MOCK", "1")
    monkeypatch.setenv("FIRECRAWL_MOCK", "1")
    monkeypatch.setenv("MAIL_DRY_RUN", "1")
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["new"] >= 1
