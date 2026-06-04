from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
FRAMES_DIR = DATA_DIR / "frames"
FRAME_COUNT = int(os.environ.get("FRAME_COUNT", "6"))
SCREEN_W = int(os.environ.get("SCREEN_W", "1280"))
SCREEN_H = int(os.environ.get("SCREEN_H", "800"))
