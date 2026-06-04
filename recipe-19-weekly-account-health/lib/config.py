from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def history_path() -> Path:
    return data_dir() / "weekly_history.json"


SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#cs-health")
USE_STRIPE_MOCK = os.environ.get("STRIPE_MOCK", "").lower() in {"1", "true", "yes"}
