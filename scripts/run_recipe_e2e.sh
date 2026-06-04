#!/usr/bin/env bash
# Run offline e2e across all recipe cookbooks; fails fast on first error.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ALLOW_LOCAL_SECRETS=0
export DATA_DIR="${DATA_DIR:-/tmp/instavm-recipe-e2e}"
export MAIL_DRY_RUN=1
export EXA_MOCK=1
export FIRECRAWL_MOCK=1
export STRIPE_MOCK=1
export GITHUB_MOCK=1
export LINEAR_MOCK=1
export LINKUP_MOCK=1
export SLACK_DRY_RUN=1
export NOTION_MOCK=1
export COMPETITOR_MOCK=1
export CARTESIA_MOCK=1
export INSTAVM_FORK_MOCK=1
cd "$ROOT"
for d in "$ROOT"/recipe-*/; do
  slug="$(basename "$d")"
  echo "==> e2e $slug"
  (
    cd "$d"
    test -x .venv/bin/pytest || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
    .venv/bin/pytest tests/test_e2e.py tests/test_ui.py -q --tb=line
  )
done
echo "All recipe e2e (+ ui) passed."
