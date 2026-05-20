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
    monkeypatch.setenv("DATA_DIR", "/tmp/vc-test")
    monkeypatch.setenv("MAIL_DRY_RUN", "1")

    def fake_search(thesis, *, limit=20, client=None):
        from integrations.exa import VCResult

        return [VCResult(url="https://vc.com", title="Test VC", snippet="Seed AI")]

    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "search_vcs", fake_search)
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["new"] >= 1
