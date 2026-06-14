import json
import time

import pytest
from fastapi.testclient import TestClient

from app import create_app
from orchestrator.config import WorkerConfig
from orchestrator.worker_pool import WorkerPool
from tests.fakes import FakeWorkerClient, fake_factory


def _config() -> WorkerConfig:
    return WorkerConfig(
        environment_id="env_test",
        environment_key="ANTHROPIC_ENV_KEY",
        workdir="/workspace",
        max_idle="30s",
        ant_version="1.12.0",
        memory_mb=2048,
        vcpu_count=2,
        egress_domains=("api.anthropic.com",),
    )


@pytest.fixture
def client(monkeypatch):
    # Dev mode: skip signature verification for the smoke flow.
    monkeypatch.setenv("WEBHOOK_VERIFY", "0")
    monkeypatch.setenv("DISPATCHER_DEBOUNCE_MS", "0")
    FakeWorkerClient.instances.clear()
    pool = WorkerPool(_config(), instavm_api_key="iv-key", client_factory=fake_factory)
    app = create_app(pool=pool)
    app.state.pool = pool
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] == "true"


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Claude Managed Agents" in resp.text


def test_webhook_schedules_worker(client):
    body = {"data": {"type": "session.status_run_started", "id": "sess_smoke"}}
    resp = client.post("/webhook", content=json.dumps(body))
    assert resp.status_code == 200
    assert resp.json()["scheduled"] == "sess_smoke"

    # Dispatch runs as a background task; pump the loop until the worker appears.
    workers = []
    for _ in range(50):
        workers = client.get("/workers").json()["workers"]
        if any(w["session_id"] == "sess_smoke" for w in workers):
            break
        time.sleep(0.02)
    assert any(w["session_id"] == "sess_smoke" for w in workers)
    # Worker microVM was spawned with only a placeholder Anthropic key.
    spawned = FakeWorkerClient.instances[0]
    assert spawned.env["ANTHROPIC_ENVIRONMENT_KEY"] == "ANTHROPIC_ENV_KEY"
    assert spawned.egress["allowed_domains"] == ["api.anthropic.com"]


def test_webhook_ignores_other_events(client):
    body = {"data": {"type": "session.status_idle", "id": "sess_x"}}
    resp = client.post("/webhook", content=json.dumps(body))
    assert resp.status_code == 200
    assert resp.json()["ignored"] == "session.status_idle"
    assert FakeWorkerClient.instances == []
