import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_transcript_json_dry_run(client):
    resp = client.post(
        "/transcript?dry_run=true",
        json={"transcript": "We lost because the champion left mid-cycle.", "deal_name": "Globex"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["postmortem"]["deal_name"] == "Globex"
