import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from lib.secrets import secret_available

pytestmark = pytest.mark.e2e


@pytest.fixture
def client():
    return TestClient(app)


def test_e2e_offline_happy_path(client, monkeypatch, tmp_path):
    """Full dry-run path without external API keys."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_LOCAL_SECRETS", "0")

    resp = client.get("/")
    assert resp.status_code == 200
    assert "Screen replay" in resp.text or "replay" in resp.text.lower()

