from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DraftStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, draft: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(draft, indent=2), encoding="utf-8")

    def load(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))
