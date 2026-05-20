"""Generate placeholder desktop frames for computer-use replay gallery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lib.config import FRAME_COUNT, FRAMES_DIR
from lib.frames import ensure_placeholder_frames


@dataclass
class CaptureResult:
    frame_count: int
    frames_dir: str


def capture_frames(*, frames_dir: Path | None = None, count: int | None = None) -> CaptureResult:
    target = frames_dir or FRAMES_DIR
    n = count if count is not None else FRAME_COUNT
    paths = ensure_placeholder_frames(target, n)
    return CaptureResult(frame_count=len(paths), frames_dir=str(target))
