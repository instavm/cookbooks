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


def test_prospect_dry_run(client, monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/tmp/cold-outbound-test")
    monkeypatch.setenv("MAIL_DRY_RUN", "1")

    def fake_research(company, *, domain="", num_results=3, client=None):
        from integrations.exa import ExaHit

        return [ExaHit(title="Launch", url="https://example.com", snippet="Big launch")]

    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "research_company", fake_research)
    resp = client.post(
        "/prospect?dry_run=true",
        json={"name": "Pat", "email": "pat@acme.com", "company": "Acme", "domain": "acme.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["research_hits"] >= 1
