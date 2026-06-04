from agent import process_transcript
from integrations.notion import append_roadmap_items


def test_append_roadmap_mock(monkeypatch):
    monkeypatch.setenv("NOTION_MOCK", "1")
    result = append_roadmap_items([{"title": "SSO", "priority": "High"}])
    assert result.appended == 1
    assert result.page_ids


def test_process_transcript_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = process_transcript("Add billing alerts", dry_run=True)
    assert result.dry_run is True
    assert result.items
