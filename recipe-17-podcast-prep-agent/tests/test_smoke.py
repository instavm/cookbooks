import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_transcript_dry_run(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    resp = client.post(
        "/transcript?dry_run=true",
        json={
            "transcript": "Host: Welcome. Guest: We discuss AI infra and deployment patterns at length.",
            "episode_title": "Ep 42",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
