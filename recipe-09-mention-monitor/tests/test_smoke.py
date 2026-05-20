import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["brand"]


def test_run_dry_run(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_hn(brand, *, limit=10, client=None):
        from integrations.hn import Mention

        return [Mention(id="hn-99", title="InstaVM", url="https://hn.com", source="hackernews", text="mention")]

    def fake_reddit(brand, *, limit=10, client=None):
        return []

    import agent

    monkeypatch.setattr(agent.hn_integration, "search_mentions", fake_hn)
    monkeypatch.setattr(agent.reddit_integration, "search_mentions", fake_reddit)
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["new"] >= 1
