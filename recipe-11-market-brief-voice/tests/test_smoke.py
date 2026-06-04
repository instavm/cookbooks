import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_run_and_audio(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LINKUP_TEST_MODE", "1")
    resp = client.post("/run?dry_run=true")
    assert resp.status_code == 200
    assert resp.json()["audio_bytes"] > 0
    audio = client.get("/audio/latest")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/")
