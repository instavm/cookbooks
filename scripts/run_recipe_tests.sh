#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export ALLOW_LOCAL_SECRETS=1
python3 scripts/validate_manifests.py
for d in "$ROOT"/recipe-*/; do
  slug="$(basename "$d")"
  echo "==> $slug"
  (
    cd "$d"
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
    .venv/bin/pytest tests/test_unit.py tests/test_smoke.py tests/test_ui.py -q --tb=line
  )
done
echo "All recipe cookbooks passed unit + smoke tests."
