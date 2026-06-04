import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from agent import review_pr
from app import app
from lib.config import sample_pr_path


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_review_pr_dry_run():
    payload = json.loads(sample_pr_path().read_text(encoding="utf-8"))
    result = review_pr(payload, dry_run=True)
    assert result.dry_run is True
    assert result.pr_number == 42
    assert "InstaVM PR Review" in result.review_markdown


def test_webhook_rejects_bad_signature_even_with_dry_run(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    client = TestClient(app)
    body = sample_pr_path().read_text(encoding="utf-8")
    resp = client.post(
        "/webhook/github?dry_run=1",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 401


def test_webhook_rejects_missing_signature(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    client = TestClient(app)
    body = sample_pr_path().read_text(encoding="utf-8")
    resp = client.post("/webhook/github", content=body)
    assert resp.status_code == 401


def test_webhook_503_when_secret_unbound(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)
    monkeypatch.setenv("ALLOW_LOCAL_SECRETS", "0")
    client = TestClient(app)
    body = sample_pr_path().read_text(encoding="utf-8")
    resp = client.post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 503


def test_webhook_accepts_valid_signature(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    client = TestClient(app)
    body = sample_pr_path().read_text(encoding="utf-8").encode()
    resp = client.post(
        "/webhook/github?dry_run=1",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body, "test-secret")},
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
