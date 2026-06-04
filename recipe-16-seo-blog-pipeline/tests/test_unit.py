from agent import generate_blog, load_preview, render_preview_html
from lib.draft_store import DraftStore


def test_generate_blog_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = generate_blog("AI agents for sales", dry_run=True)
    assert result.dry_run is True
    assert "AI agents" in result.draft["title"]
    assert load_preview() is not None


def test_draft_store_roundtrip(tmp_path):
    store = DraftStore(tmp_path / "draft.json")
    store.save({"title": "T", "body_markdown": "Body"})
    loaded = store.load()
    assert loaded["title"] == "T"


def test_render_preview_html():
    html = render_preview_html({"title": "Hello", "meta_description": "Meta", "body_markdown": "Line"})
    assert "<h1>Hello</h1>" in html
    assert "Meta" in html
