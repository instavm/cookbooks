import json
from pathlib import Path

from agent import process_transcript, run_followup


def test_process_transcript_dry_run():
    payload = {
        "title": "Intro call",
        "attendee_name": "Jane",
        "attendee_email": "jane@acme.vc",
        "transcript": "We agreed to share the deck.",
    }
    result = process_transcript(payload, dry_run=True)
    assert result.dry_run is True
    assert "Jane" in result.body
    assert result.saved_path is None


def test_process_transcript_saves(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    class FakeLLM:
        def complete_json(self, system, user):
            return {
                "subject": "Thanks for today",
                "body": "Hi Jane, great chat.",
                "action_items": ["Send deck"],
            }

    payload = {
        "title": "Intro",
        "attendee_name": "Jane",
        "attendee_email": "jane@acme.vc",
        "transcript": "Long transcript text.",
    }
    result = process_transcript(payload, dry_run=False, llm=FakeLLM())
    assert result.saved_path is not None
    saved = json.loads(Path(result.saved_path).read_text())
    assert saved["subject"] == "Thanks for today"


def test_run_followup_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = run_followup(dry_run=True)
    assert result.dry_run is True
    assert result.new == 1
