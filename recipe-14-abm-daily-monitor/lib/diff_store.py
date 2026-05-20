from __future__ import annotations

import json
from pathlib import Path


class FingerprintStore:
    """Per-account content fingerprints for ABM diffing."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._data: dict[str, str] = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._data = {}
            self.flush()

    def get(self, domain: str) -> str | None:
        return self._data.get(domain)

    def set(self, domain: str, fingerprint: str) -> None:
        self._data[domain] = fingerprint

    def is_new(self, domain: str, fingerprint: str) -> bool:
        return self._data.get(domain) != fingerprint

    def flush(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
