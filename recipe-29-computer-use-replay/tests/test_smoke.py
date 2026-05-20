import os

import pytest
from fastapi.testclient import TestClient

# Import after DATA_DIR is set in conftest
from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] == "true"


def test_gallery(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "frame_" in resp.text


def test_capture(client):
    resp = client.post("/capture")
    assert resp.status_code == 200
    assert resp.json()["frame_count"] >= 1
