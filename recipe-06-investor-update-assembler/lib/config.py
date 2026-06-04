from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def kpi_history_path() -> Path:
    return data_dir() / "kpi_history.json"


def updates_dir() -> Path:
    return data_dir() / "updates"


GITHUB_REPO = os.environ.get("GITHUB_REPO", "org/repo")
STRIPE_TEST_MODE = os.environ.get("STRIPE_TEST_MODE", "").lower() in {"1", "true", "yes"}
