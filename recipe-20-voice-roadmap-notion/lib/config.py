from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def intake_path() -> Path:
    return data_dir() / "transcript_intake.json"


NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "roadmap-db-mock")
USE_NOTION_MOCK = os.environ.get("NOTION_MOCK", "").lower() in {"1", "true", "yes"}
