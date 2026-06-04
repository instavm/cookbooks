from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/mnt/data"))


def followups_dir() -> Path:
    return data_dir() / "followups"


SAMPLE_TRANSCRIPT = {
    "title": "Seed intro with Jane",
    "attendee_email": "jane@acme.vc",
    "attendee_name": "Jane Investor",
    "transcript": (
        "Founder: Thanks for joining.\n"
        "Jane: Happy to learn more about your AI infra platform.\n"
        "Founder: We will send the deck by Friday.\n"
        "Jane: Please include customer references."
    ),
}
