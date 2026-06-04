from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def briefings_dir() -> Path:
    return data_dir() / "briefings"


SAMPLE_ATTENDEE = {
    "attendees": [
        {
            "name": "Jane Investor",
            "email": "jane@acme.vc",
            "organization": "Acme Ventures",
        }
    ],
    "startTime": "2026-05-20T15:00:00Z",
    "title": "Seed intro call",
}
