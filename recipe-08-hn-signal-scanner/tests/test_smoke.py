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
    monkeypatch.setenv("DATA_DIR", "/tmp/hn-test")
    monkeypatch.setenv("MAIL_DRY_RUN", "1")

    def fake_fetch(query, *, limit=30, client=None):
        from integrations.hn import Story

        return [Story(id="1", title="Test", url="https://example.com", points=10)]

    import integrations.hn as hn

    monkeypatch.setattr(hn, "fetch_stories", fake_fetch)
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["new"] >= 1
