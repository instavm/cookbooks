from agent import prepare_episode
from integrations.cartesia import synthesize_intro


def test_prepare_episode_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = prepare_episode("Host: Welcome. Guest: Thanks for having me.", dry_run=True)
    assert result.dry_run is True
    assert result.show_notes["episode_title"]


def test_cartesia_stub_default(monkeypatch):
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    monkeypatch.setenv("CARTESIA_STUB", "1")
    tts = synthesize_intro("Welcome to the show.")
    assert tts.stub is True
    assert b"cartesia-stub" in tts.audio_bytes


def test_prepare_with_tts_stub(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    class FakeLLM:
        def complete_json(self, system, user):
            return {
                "episode_title": "Ep 1",
                "summary": "Great chat",
                "chapters": [],
                "key_quotes": [],
                "guest_bio": None,
                "social_posts": [],
                "intro_script": "Welcome!",
            }

    result = prepare_episode("Long transcript text here.", with_tts=True, llm=FakeLLM())
    assert result.tts_stub is True
    assert result.tts_bytes > 0
