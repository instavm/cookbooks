import base64
import hashlib
import hmac
import json
import time

import asyncio

import pytest

from orchestrator.config import WorkerConfig
from orchestrator.signature import (
    WebhookError,
    extract_session_event,
    verify_and_parse,
)
from orchestrator.worker_pool import WorkerPool, build_worker_command
from tests.fakes import FakeWorkerClient, fake_factory


def _config() -> WorkerConfig:
    return WorkerConfig(
        environment_id="env_test",
        environment_key="ANTHROPIC_ENV_KEY",  # placeholder, injected at egress
        workdir="/workspace",
        max_idle="30s",
        ant_version="1.12.0",
        memory_mb=2048,
        vcpu_count=2,
        egress_domains=("api.anthropic.com",),
    )


def _signed_headers(body: bytes, key: str) -> dict[str, str]:
    webhook_id = "msg_1"
    ts = str(int(time.time()))
    secret = key[len("whsec_"):] if key.startswith("whsec_") else key
    try:
        key_bytes = base64.b64decode(secret)
    except Exception:  # pragma: no cover
        key_bytes = secret.encode()
    signed = b"%s.%s.%s" % (webhook_id.encode(), ts.encode(), body)
    sig = base64.b64encode(hmac.new(key_bytes, signed, hashlib.sha256).digest()).decode()
    return {
        "webhook-id": webhook_id,
        "webhook-timestamp": ts,
        "webhook-signature": f"v1,{sig}",
    }


def test_build_worker_command_uses_poller_and_workdir():
    cmd = build_worker_command(_config())
    assert "ant beta:worker poll" in cmd
    assert '--workdir "/workspace"' in cmd
    assert '--max-idle "30s"' in cmd
    assert "anthropic-cli/releases/download/v1.12.0" in cmd


def test_extract_session_event_reads_data_block():
    payload = {"type": "webhook", "data": {"type": "session.status_run_started", "id": "sess_42"}}
    assert extract_session_event(payload) == ("session.status_run_started", "sess_42")


def test_verify_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)
    body = json.dumps({"data": {"type": "session.status_run_started", "id": "s1"}}).encode()
    headers = _signed_headers(body, "whsec_" + base64.b64encode(b"secret-key").decode())
    headers["webhook-signature"] = "v1,not-the-right-signature"
    with pytest.raises(WebhookError):
        verify_and_parse(body, headers, "whsec_" + base64.b64encode(b"secret-key").decode())


def test_verify_accepts_valid_signature(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)
    monkeypatch.setattr("orchestrator.signature._verify_with_sdk", lambda *a, **k: False)
    key = "whsec_" + base64.b64encode(b"top-secret-value").decode()
    body = json.dumps({"data": {"type": "session.status_run_started", "id": "s9"}}).encode()
    headers = _signed_headers(body, key)
    payload = verify_and_parse(body, headers, key)
    assert extract_session_event(payload) == ("session.status_run_started", "s9")


def test_verify_fails_closed_without_key(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)
    body = b"{}"
    with pytest.raises(WebhookError):
        verify_and_parse(body, {}, "ANTHROPIC_WHSEC")  # placeholder = unbound


def test_pool_spawns_worker_with_egress_and_no_naked_key():
    FakeWorkerClient.instances.clear()
    pool = WorkerPool(_config(), instavm_api_key="iv-key", client_factory=fake_factory)
    info = asyncio.run(pool.ensure_worker("sess_abc"))
    assert info.status == "running"
    assert info.vm_id == "vm-1"
    client = FakeWorkerClient.instances[0]
    # Worker carries only the placeholder env key — never a real Anthropic secret.
    assert client.env["ANTHROPIC_ENVIRONMENT_KEY"] == "ANTHROPIC_ENV_KEY"
    assert client.env["ANTHROPIC_SESSION_ID"] == "sess_abc"
    assert client.egress["allowed_domains"] == ["api.anthropic.com"]
    assert "ant beta:worker poll" in client.commands[0]


def test_pool_is_idempotent_per_session():
    FakeWorkerClient.instances.clear()
    pool = WorkerPool(_config(), instavm_api_key="iv-key", client_factory=fake_factory)

    async def run_twice():
        await pool.ensure_worker("dup")
        await pool.ensure_worker("dup")

    asyncio.run(run_twice())
    assert len(FakeWorkerClient.instances) == 1
    assert pool.count_active() == 1
