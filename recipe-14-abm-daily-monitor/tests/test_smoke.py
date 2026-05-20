import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_accounts_and_run_dry(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_DRY_RUN", "1")

    def fake_fetch(domain, *, client=None):
        from integrations.linkup import AccountNews

        return AccountNews(domain=domain, answer="Fresh signal", fingerprint=f"fp-{domain}")

    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "fetch_account_news", fake_fetch)

    resp = client.post("/accounts", json={"accounts": ["acme.com"]})
    assert resp.status_code == 200

    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    assert resp.json()["new_signal"] >= 1
