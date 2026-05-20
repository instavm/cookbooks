import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from agent import build_briefing, parse_cal_event, run_briefing
from app import app
from integrations.exa import ResearchHit, research_attendee


def _cal_sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_research_attendee_parses(monkeypatch):
    monkeypatch.setenv("EXA_MOCK", "0")
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)

    fake_exa = MagicMock()
    fake_exa.search_and_contents.return_value = SimpleNamespace(
        results=[SimpleNamespace(url="https://x.com", title="News", text="Raised seed")]
    )
    hits = research_attendee("Jane", "Acme", "jane@acme.vc", exa=fake_exa)
    assert len(hits) >= 1
    assert hits[0].url == "https://x.com"


def test_parse_cal_event():
    event = {
        "attendees": [{"name": "Jane", "email": "jane@acme.vc", "organization": "Acme"}],
        "startTime": "2026-05-20T15:00:00Z",
        "title": "Intro",
    }
    parsed = parse_cal_event(event)
    assert parsed["attendee_name"] == "Jane"
    assert parsed["company"] == "Acme"


def test_build_briefing_dry_run(monkeypatch):
    def fake_research(name, company, email, *, exa=None):
        return [ResearchHit(url="https://x.com", title="Hit", snippet="Snippet")]

    monkeypatch.setattr("agent.research_attendee", fake_research)
    result = build_briefing(
        {"attendees": [{"name": "Jane", "email": "j@x.com", "organization": "Acme"}]},
        dry_run=True,
    )
    assert result.dry_run is True
    assert "Jane" in result.briefing


def test_cal_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.setenv("CAL_WEBHOOK_SECRET", "test-secret")
    client = TestClient(app)
    body = json.dumps({"attendees": [{"name": "X", "email": "x@y.com"}]}).encode()
    resp = client.post(
        "/webhook/cal",
        content=body,
        headers={"X-Cal-Signature-256": "deadbeef"},
    )
    assert resp.status_code == 401


def test_cal_webhook_503_when_secret_unbound(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.delenv("CAL_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("DEPLOY_SMOKE", raising=False)
    monkeypatch.setenv("ALLOW_LOCAL_SECRETS", "0")
    client = TestClient(app)
    resp = client.post("/webhook/cal", content=b"{}")
    assert resp.status_code == 503


def test_cal_webhook_accepts_valid_signature(monkeypatch):
    monkeypatch.setenv("WEBHOOK_VERIFY", "1")
    monkeypatch.setenv("CAL_WEBHOOK_SECRET", "test-secret")

    def fake_research(name, company, email, *, exa=None):
        return [ResearchHit(url="https://x.com", title="Hit", snippet="Snippet")]

    monkeypatch.setattr("agent.research_attendee", fake_research)
    client = TestClient(app)
    body = json.dumps({"attendees": [{"name": "Jane", "email": "j@x.com", "organization": "Acme"}]}).encode()
    resp = client.post(
        "/webhook/cal?dry_run=1",
        content=body,
        headers={"X-Cal-Signature-256": _cal_sign(body, "test-secret")},
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True


def test_run_briefing_dry_run(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def fake_research(name, company, email, *, exa=None):
        return [ResearchHit(url="https://x.com", title="Hit", snippet="Snippet")]

    monkeypatch.setattr("agent.research_attendee", fake_research)
    result = run_briefing(dry_run=True)
    assert result.dry_run is True
    assert result.new == 1
