from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def routed_path() -> Path:
    return data_dir() / "routed_feedback.json"


LINEAR_TEAM_ID = os.environ.get("LINEAR_TEAM_ID", "team-demo")
ROUTE_THRESHOLD = os.environ.get("ROUTE_CATEGORY", "bug")
