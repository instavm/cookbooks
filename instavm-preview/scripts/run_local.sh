#!/usr/bin/env bash
# Run InstaVM Preview locally against api.instavm.io (prod).
# Loads INSTAVM_API_KEY from ~/Documents/projects/.instavm (prod Pro key).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PREVIEW_LOCAL=1
export PREVIEW_PUBLIC_ORIGIN="${PREVIEW_PUBLIC_ORIGIN:-http://127.0.0.1:8000}"
export PREVIEW_COOKIE_SECURE="${PREVIEW_COOKIE_SECURE:-0}"
# Default OpenAI plan for Preview builds (override with OPENAI_MODEL=...).
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.4-nano}"

# Prefer package venv if present.
if [[ -d "$ROOT/.venv" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

# Ensure Agents SDK + InstaVM provider are compatible for local runs.
python3 - <<'PY'
import importlib.util
import subprocess
import sys

need = []
if importlib.util.find_spec("instavm") is None:
    need.append("instavm")
else:
    import inspect
    from instavm.integrations.openai_agents import InstaVMSandboxSession
    if "for_write" not in inspect.signature(InstaVMSandboxSession.normalize_path).parameters:
        need.append("instavm-for_write")
try:
    import agents
    ver = getattr(agents, "__version__", "0")
    if tuple(int(x) for x in ver.split(".")[:2]) < (0, 18):
        need.append("agents")
except Exception:
    need.append("agents")

if need:
    print("Installing local deps for Preview:", need)
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "/Users/abhishekanand/Documents/projects/sandbox_client",
        "openai-agents>=0.18.3,<0.19",
    ])
PY

python3 - <<'PY'
from pathlib import Path
import os
import sys

root = Path(".").resolve()
sys.path.insert(0, str(root))
os.environ["PREVIEW_LOCAL"] = "1"

from app.local_secrets import (
    apply_local_secrets,
    PROJECTS_INSTAVM_KEY,
    PROJECTS_OPENAI_KEY,
)

loaded = apply_local_secrets(force=True)
instavm = (os.environ.get("INSTAVM_API_KEY") or "").strip()
openai = (os.environ.get("OPENAI_API_KEY") or "").strip()

if not instavm:
    print(
        f"Missing INSTAVM_API_KEY. Put your prod Pro key in:\n  {PROJECTS_INSTAVM_KEY}\n"
        "or export INSTAVM_API_KEY=...",
        file=sys.stderr,
    )
    sys.exit(1)

if not openai:
    print(
        f"Missing OPENAI_API_KEY. Put it in:\n  {PROJECTS_OPENAI_KEY}\n"
        "or export OPENAI_API_KEY=sk-...\n"
        "or add it to cookbooks/instavm-preview/.env",
        file=sys.stderr,
    )
    sys.exit(1)

# Quick auth check against prod
try:
    from instavm import InstaVM
    summary = InstaVM(api_key=instavm).credits.summary()
    remaining = summary.get("dollars", {}).get("remaining")
    print(f"InstaVM auth OK (remaining ${remaining})")
except Exception as exc:
    print(f"InstaVM auth failed: {exc}", file=sys.stderr)
    sys.exit(1)

print(f"OPENAI_API_KEY loaded from {PROJECTS_OPENAI_KEY if loaded['openai'] else 'env'} ({len(openai)} chars)")
print(f"OPENAI_MODEL={os.environ.get('OPENAI_MODEL', 'gpt-5.4-nano')}")
print(f"INSTAVM key file: {PROJECTS_INSTAVM_KEY}")
PY

PORT="${PORT:-8000}"
echo "Starting InstaVM Preview on http://127.0.0.1:${PORT}"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload
