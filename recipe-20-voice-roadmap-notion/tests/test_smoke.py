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


def test_webhook_transcript_dry_run(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOTION_MOCK", "1")
    resp = client.post(
        "/webhook/transcript?dry_run=true",
        json={"transcript": "We should add SSO and improve onboarding."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert len(body["items"]) >= 1
