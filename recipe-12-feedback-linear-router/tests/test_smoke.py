import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_slack_webhook_fixture(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "fixtures" / "slack_event.json").read_text()
    )
    resp = client.post("/webhook/slack?dry_run=true", json=fixture)
    assert resp.status_code == 200
    body = resp.json()
    assert body["routed"] is True
    assert body["dry_run"] is True
