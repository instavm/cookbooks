from pathlib import Path

from lib.frames import ensure_placeholder_frames, frame_gallery_html


def test_ensure_placeholder_frames(tmp_path: Path):
    paths = ensure_placeholder_frames(tmp_path, 3)
    assert len(paths) == 3
    assert all(p.is_file() for p in paths)


def test_gallery_html(tmp_path: Path):
    paths = ensure_placeholder_frames(tmp_path, 2)
    html = frame_gallery_html(paths, screen_w=1280, screen_h=800)
    assert "frame_000.png" in html
    assert "1280" in html and "800" in html
