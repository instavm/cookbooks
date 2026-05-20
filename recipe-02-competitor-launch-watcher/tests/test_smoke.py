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
    monkeypatch.setenv("DATA_DIR", "/tmp/competitor-test")

    def fake_fetch(competitors, *, client=None):
        from integrations.competitors import PageSnapshot

        return [PageSnapshot(url="https://a.com", name="A", titles=["Launch"])]

    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "fetch_competitors", fake_fetch)
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["fetched"] >= 1
