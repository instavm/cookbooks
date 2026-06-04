from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class JsonStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._items: set[str] = set(json.loads(self.path.read_text(encoding="utf-8")))
        else:
            self._items = set()
            self.flush()

    def seen(self, key: str) -> bool:
        return key in self._items

    def filter_new(self, keys: Iterable[str]) -> list[str]:
        return [k for k in keys if k not in self._items]

    def mark_many(self, keys: Iterable[str]) -> None:
        self._items.update(keys)

    def flush(self) -> None:
        self.path.write_text(json.dumps(sorted(self._items), indent=2), encoding="utf-8")
