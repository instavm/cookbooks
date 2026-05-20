"""Deterministic replay — configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASSETTE_PATH = ROOT / "fixtures" / "cassette.jsonl"
