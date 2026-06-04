#!/usr/bin/env bash
# Scan recipe source for accidentally committed secrets (excludes .venv).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PATTERNS=(
  'sk-[a-zA-Z0-9]{20,}'
  'instavm_sk_[a-zA-Z0-9_-]{20,}'
  'ghp_[a-zA-Z0-9]{20,}'
  'xox[baprs]-[a-zA-Z0-9-]{10,}'
  'AKIA[A-Z0-9]{16}'
  '-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----'
)

FAIL=0
for pat in "${PATTERNS[@]}"; do
  hits=$(rg -n "$pat" \
    --glob 'recipe-*/**' \
    --glob '!**/.venv/**' \
    --glob '!**/fixtures/**' \
    --glob '!**/*.jsonl' \
    . 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo "FAIL pattern: $pat"
    echo "$hits"
    FAIL=1
  fi
done

# Block tracked env / key files
for f in .env .openai .anthropic .mailtrap; do
  if [ -f "$ROOT/$f" ] && git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    echo "FAIL tracked secret file: $f"
    FAIL=1
  fi
done

if [ "$FAIL" -eq 0 ]; then
  echo "Secret scan passed (no high-confidence credential patterns in recipe source)."
  exit 0
fi
exit 1
