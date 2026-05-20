from __future__ import annotations

import os
from pathlib import Path


def fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"


def sample_pr_path() -> Path:
    return fixtures_dir() / "pr_opened.json"
