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


def test_run_dry_run(client):
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["new"] == 1


def test_webhook_transcript_dry_run(client):
    payload = {
        "title": "Intro",
        "attendee_name": "Jane",
        "attendee_email": "jane@acme.vc",
        "transcript": "We will follow up next week.",
    }
    resp = client.post("/webhook/transcript?dry_run=true", json=payload)
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
    assert "Jane" in resp.json()["body"]
