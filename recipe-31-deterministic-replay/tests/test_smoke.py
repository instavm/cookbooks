import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json()["ok"] == "true"


def test_replay_endpoint(client):
    resp = client.post("/replay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "REPLAY_OK"
    assert body["deterministic"] is True
