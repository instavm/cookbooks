from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def emailed_path() -> Path:
    return data_dir() / "already_emailed.json"


DIGEST_TO = os.environ.get("DIGEST_TO", "you@example.com")
MAIL_FROM = os.environ.get("MAIL_FROM", "outbound@instavm.io")
