from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


GITHUB_REPO = os.environ.get("GITHUB_REPO", "instavm/cookbooks")
LINEAR_TEAM = os.environ.get("LINEAR_TEAM", "ENG")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#engineering")
USE_GITHUB_MOCK = os.environ.get("GITHUB_MOCK", "").lower() in {"1", "true", "yes"}
USE_LINEAR_MOCK = os.environ.get("LINEAR_MOCK", "").lower() in {"1", "true", "yes"}
