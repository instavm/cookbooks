from __future__ import annotations

import struct
import zlib
from pathlib import Path

from lib.ui import replay_gallery


def _png_with_size(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    raw: list[int] = []
    r, g, b = rgb
    row = bytes([r, g, b] * width)
    for _ in range(height):
        raw.append(0)
        raw.extend(row)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def ensure_placeholder_frames(frames_dir: Path, count: int = 6) -> list[Path]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    palette = [(220, 80, 80), (80, 160, 220), (90, 190, 120), (210, 170, 60), (180, 100, 200), (120, 120, 120)]
    paths: list[Path] = []
    for i in range(count):
        path = frames_dir / f"frame_{i:03d}.png"
        if not path.is_file():
            path.write_bytes(_png_with_size(320, 200, palette[i % len(palette)]))
        paths.append(path)
    return paths


def frame_gallery_html(frame_paths: list[Path], *, screen_w: int, screen_h: int) -> str:
    return replay_gallery(
        title="Computer-use screen replay",
        meta=f"Desktop profile {screen_w}×{screen_h} — captured frames from the agent session.",
        frame_names=[p.name for p in frame_paths],
    )
