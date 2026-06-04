from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def seen_path() -> Path:
    return data_dir() / "seen_mentions.json"


BRAND_NAME = os.environ.get("BRAND_NAME", "InstaVM")
SCORE_THRESHOLD = int(os.environ.get("SCORE_THRESHOLD", "7"))
MAX_MENTIONS = int(os.environ.get("MAX_MENTIONS", "20"))
