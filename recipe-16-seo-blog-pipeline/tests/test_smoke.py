import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_topic_and_preview(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    resp = client.post("/topic?dry_run=true", json={"topic": "microVM security"})
    assert resp.status_code == 200
    resp = client.get("/preview")
    assert resp.status_code == 200
    assert "microVM" in resp.text
