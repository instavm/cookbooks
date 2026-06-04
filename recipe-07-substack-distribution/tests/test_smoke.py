import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_publish_and_preview(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIRECRAWL_TEST_MODE", "1")
    resp = client.post(
        "/publish?dry_run=true",
        json={"url": "https://example.substack.com/p/hello"},
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
    preview = client.get("/preview")
    assert preview.status_code == 200
    assert "LinkedIn" in preview.text
