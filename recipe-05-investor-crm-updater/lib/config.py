from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def crm_path() -> Path:
    return data_dir() / "crm.json"


SAMPLE_EMAIL_SIGNAL = {
    "from_name": "Jane Investor",
    "from_email": "jane@acme.vc",
    "subject": "Re: Seed round intro",
    "body_preview": "Thanks for the deck. Happy to schedule a partner meeting next week.",
}
