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


def test_run_dry_run(client, monkeypatch):
    def fake_research(name, company, email, *, client=None):
        from integrations.exa import ResearchHit

        return [ResearchHit(url="https://x.com", title="News", snippet="Seed round")]

    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "research_attendee", fake_research)
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["new"] == 1


def test_webhook_cal_dry_run(client, monkeypatch):
    def fake_research(name, company, email, *, client=None):
        from integrations.exa import ResearchHit

        return [ResearchHit(url="https://x.com", title="News", snippet="Seed round")]

    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "research_attendee", fake_research)
    payload = {
        "attendees": [{"name": "Jane", "email": "jane@acme.vc", "organization": "Acme"}],
        "startTime": "2026-05-20T15:00:00Z",
        "title": "Intro",
    }
    resp = client.post("/webhook/cal?dry_run=true", json=payload)
    assert resp.status_code == 200
    assert resp.json()["attendee_name"] == "Jane"
