from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def audio_dir() -> Path:
    return data_dir() / "audio"


def heard_path() -> Path:
    return data_dir() / "heard_stories.json"


def latest_audio_path() -> Path:
    return audio_dir() / "latest.mp3"


LINKUP_TEST_MODE = os.environ.get("LINKUP_TEST_MODE", "").lower() in {"1", "true", "yes"}
CARTESIA_ENABLED = os.environ.get("CARTESIA_ENABLED", "").lower() in {"1", "true", "yes"}
