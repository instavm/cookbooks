from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] == "true"


def test_fork_mocked(client, monkeypatch):
    class _FakeExecResult:
        stdout = "sandbox:fork-alpha"
        exit_code = 0

    class _FakeSession:
        async def exec(self, *args, **kwargs):
            return _FakeExecResult()

    class _FakeClient:
        n = 0

        async def create(self, **kwargs):
            self.n += 1
            return _FakeSession()

        async def delete(self, session):
            return session

    async def fake_run_fork(**kwargs):
        from lib.sandbox_fork import ForkResult, ChildResult

        return ForkResult(
            children=[
                ChildResult(task="fork-alpha", stdout="sandbox:fork-alpha", exit_code=0),
                ChildResult(task="fork-beta", stdout="sandbox:fork-beta", exit_code=0),
            ]
        )

    monkeypatch.setattr("agent.run_fork", fake_run_fork)
    resp = client.post("/fork", json={"tasks": ["fork-alpha", "fork-beta"]})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["children"]) == 2
