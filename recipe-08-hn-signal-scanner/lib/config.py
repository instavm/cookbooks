from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def seen_path() -> Path:
    return data_dir() / "seen_stories.json"


DIGEST_TO = os.environ.get("DIGEST_TO", "you@example.com")
HN_QUERY = os.environ.get("HN_QUERY", "AI agent OR LLM OR sandbox")
MAX_STORIES = int(os.environ.get("MAX_STORIES", "30"))
