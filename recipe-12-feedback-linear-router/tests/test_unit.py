import json
from pathlib import Path

from agent import handle_slack_event
from integrations.linear import create_issue


def _fixture(name: str) -> dict:
    path = Path(__file__).resolve().parents[1] / "fixtures" / name
    return json.loads(path.read_text())


def test_linear_mock(monkeypatch):
    monkeypatch.setenv("LINEAR_MOCK", "1")
    issue = create_issue(title="Test bug", description="Details")
    assert issue.id.startswith("mock-")


def test_slack_url_verification():
    result = handle_slack_event({"type": "url_verification", "challenge": "abc123"})
    assert result == {"challenge": "abc123"}


def test_slack_event_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    body = _fixture("slack_event.json")
    result = handle_slack_event(body, dry_run=True)
    assert result.skipped is False
    assert result.routed is True
    assert result.category == "bug"


def test_slack_skips_short_message(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    body = {"event": {"type": "message", "text": "hi", "channel": "C1", "ts": "1.0"}}
    result = handle_slack_event(body, dry_run=True)
    assert result.skipped is True
