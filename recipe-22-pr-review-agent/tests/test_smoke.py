import json

import pytest
from fastapi.testclient import TestClient

from app import app
from lib.config import sample_pr_path


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] == "true"


def test_webhook_github_fixture(client):
    payload = json.loads(sample_pr_path().read_text(encoding="utf-8"))
    resp = client.post("/webhook/github?dry_run=true", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["pr_number"] == 42
    assert "review_markdown" in body
