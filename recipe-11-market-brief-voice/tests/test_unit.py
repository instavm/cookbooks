from agent import read_latest_audio, run_brief
from integrations.cartesia import synthesize
from integrations.linkup import fetch_news


def test_linkup_mock(monkeypatch):
    monkeypatch.setenv("LINKUP_TEST_MODE", "1")
    stories = fetch_news()
    assert len(stories) >= 1
    assert stories[0].content


def test_cartesia_stub():
    result = synthesize("Hello market brief")
    assert result.stub is True
    assert len(result.audio) > 0


def test_run_brief_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LINKUP_TEST_MODE", "1")
    result = run_brief(dry_run=True)
    assert result.dry_run is True
    assert result.skipped is False
    assert result.audio_bytes > 0
    assert read_latest_audio() is not None


def test_run_brief_skips_when_heard(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LINKUP_TEST_MODE", "1")
    from lib.config import heard_path
    from lib.store import JsonStore

    store = JsonStore(heard_path())
    store.mark_many(s.id for s in fetch_news())
    store.flush()
    result = run_brief(dry_run=True)
    assert result.skipped is True
