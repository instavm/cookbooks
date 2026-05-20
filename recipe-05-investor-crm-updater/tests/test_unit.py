import json
from pathlib import Path

from agent import process_email_signal, run_crm_update
from lib.config import crm_path
from lib.store import CrmStore


def test_crm_store_upsert(tmp_path: Path):
    store = CrmStore(tmp_path / "crm.json")
    saved = store.upsert("jane@acme.vc", {"name": "Jane", "stage": "intro"})
    assert saved["email"] == "jane@acme.vc"
    updated = store.upsert("jane@acme.vc", {"stage": "interested"})
    assert updated["stage"] == "interested"
    assert updated["name"] == "Jane"


def test_process_email_signal_dry_run():
    signal = {
        "from_name": "Jane Investor",
        "from_email": "jane@acme.vc",
        "subject": "Re: intro",
        "body_preview": "Let's schedule next week.",
    }
    result = process_email_signal(signal, dry_run=True)
    assert result.dry_run is True
    assert result.record["email"] == "jane@acme.vc"


def test_process_email_signal_upserts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    class FakeLLM:
        def complete_json(self, system, user):
            return {
                "name": "Jane Investor",
                "email": "jane@acme.vc",
                "company": "Acme",
                "title": "Partner",
                "stage": "interested",
                "sentiment": "positive",
                "summary": "Wants partner meeting.",
            }

    signal = {
        "from_name": "Jane Investor",
        "from_email": "jane@acme.vc",
        "subject": "Re: intro",
        "body_preview": "Let's schedule next week.",
    }
    result = process_email_signal(signal, dry_run=False, llm=FakeLLM())
    assert result.created is True
    saved = json.loads(crm_path().read_text())
    assert "jane@acme.vc" in saved


def test_run_crm_update_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = run_crm_update(dry_run=True)
    assert result.dry_run is True
    assert result.new == 1
