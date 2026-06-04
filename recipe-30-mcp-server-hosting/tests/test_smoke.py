import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json()["ok"] == "true"


def test_mcp_initialize(client):
    resp = client.post(
        "/mcp/message",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["serverInfo"]["name"] == "recipe-30-mcp-stub"


def test_mcp_tools_list(client):
    resp = client.post(
        "/mcp/message",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert "ping" in names
