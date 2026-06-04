from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_history(path: Path) -> list[dict[str, Any]]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def append_entry(path: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    history = load_history(path)
    history.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return history
