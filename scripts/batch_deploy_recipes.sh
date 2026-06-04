#!/usr/bin/env bash
# Deploy recipe cookbooks in batches of 4: deploy -> health check -> terminate VM.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BATCH_SIZE=4
LOG_DIR="${ROOT}/.deploy-batch-logs"
mkdir -p "$LOG_DIR"

unset INSTAVM_API_KEY

RECIPES=()
while IFS= read -r d; do RECIPES+=("$d"); done < <(find "$ROOT" -maxdepth 1 -type d -name 'recipe-*' | sort)

deploy_one() {
  local dir="$1"
  local slug
  slug="$(basename "$dir")"
  local log="$LOG_DIR/${slug}.log"
  local result="$LOG_DIR/${slug}.result"

  (
    echo "=== DEPLOY $slug $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    cd "$dir" || exit 1

    if ! instavm deploy --plan . >/dev/null 2>&1; then
      echo "PLAN_FAIL"
      exit 0
    fi

    # Deploy-smoke mode: dummy vault placeholders, skip vault binding, all upstream mocks on.
    local extra_env=(
      --no-vault
      --no-setup-vault
      --env "ALLOW_LOCAL_SECRETS=0"
      --env "DEPLOY_SMOKE=1"
      --env "MAIL_DRY_RUN=1"
      --env "SLACK_DRY_RUN=1"
      --env "STRIPE_MOCK=1"
      --env "GITHUB_MOCK=1"
      --env "LINEAR_MOCK=1"
      --env "EXA_MOCK=1"
      --env "FIRECRAWL_MOCK=1"
      --env "NOTION_MOCK=1"
      --env "COMPETITOR_MOCK=1"
      --env "LINKUP_MOCK=1"
      --env "INSTAVM_FORK_MOCK=1"
      --env "OPENAI_API_KEY=OPENAI_KEY"
      --env "ANTHROPIC_API_KEY=ANTHROPIC_KEY"
      --env "EXA_API_KEY=EXA_KEY"
      --env "STRIPE_KEY=STRIPE_KEY"
      --env "GITHUB_TOKEN=GITHUB_KEY"
      --env "LINEAR_API_KEY=LINEAR_KEY"
      --env "NOTION_TOKEN=NOTION_KEY"
      --env "MAILTRAP_API_TOKEN=MAILTRAP_KEY"
    )

    if ! out=$(instavm deploy . -y --json "${extra_env[@]}" 2>&1); then
      echo "DEPLOY_FAIL"
      echo "$out"
      exit 0
    fi

    json_line=$(echo "$out" | grep '^{' | tail -1)
    if [ -z "$json_line" ]; then
      echo "NO_JSON"
      echo "$out"
      exit 0
    fi

    vm_id=$(echo "$json_line" | python3 -c "import sys,json; print(json.load(sys.stdin).get('vm_id',''))")
    health_url=$(echo "$json_line" | python3 -c "import sys,json; print(json.load(sys.stdin).get('healthcheck_url',''))")
    share_url=$(echo "$json_line" | python3 -c "import sys,json; print(json.load(sys.stdin).get('share_url',''))")

    echo "VM_ID=$vm_id"
    echo "SHARE=$share_url"
    echo "HEALTH=$health_url"

    if [ -n "$health_url" ]; then
      for i in 1 2 3 4 5; do
        if curl -sf --max-time 15 "$health_url" >/dev/null 2>&1; then
          echo "HEALTH_OK"
          break
        fi
        sleep 3
      done
      if ! curl -sf --max-time 15 "$health_url" >/dev/null 2>&1; then
        echo "HEALTH_FAIL"
        curl -s --max-time 15 "$health_url" || true
      fi
    fi

    if [ -n "$vm_id" ]; then
      if instavm rm "$vm_id" 2>&1; then
        echo "RM_OK"
      else
        echo "RM_FAIL"
      fi
    fi

    echo "DONE"
  ) >"$log" 2>&1

  if grep -q "HEALTH_OK" "$log" && grep -q "RM_OK" "$log"; then
    echo "OK|$slug|$(grep '^VM_ID=' "$log" | tail -1 | cut -d= -f2-)" >"$result"
  elif grep -q "^VM_ID=" "$log"; then
    echo "PARTIAL|$slug|$(grep '^VM_ID=' "$log" | tail -1 | cut -d= -f2-)" >"$result"
  elif grep -q "DEPLOY_FAIL" "$log"; then
    echo "FAIL|$slug|deploy" >"$result"
  elif grep -q "PLAN_FAIL" "$log"; then
    echo "FAIL|$slug|plan" >"$result"
  elif grep -q "HEALTH_FAIL" "$log"; then
    echo "FAIL|$slug|health" >"$result"
  else
    echo "FAIL|$slug|unknown" >"$result"
  fi
}

export -f deploy_one
export ROOT LOG_DIR

total=${#RECIPES[@]}
echo "Deploying $total recipes in batches of $BATCH_SIZE..."

ok=0
partial=0
fail=0

for ((i=0; i<total; i+=BATCH_SIZE)); do
  batch=("${RECIPES[@]:i:BATCH_SIZE}")
  batch_num=$((i/BATCH_SIZE + 1))
  echo ""
  echo "========== BATCH $batch_num (${#batch[@]} recipes) =========="
  pids=()
  for dir in "${batch[@]}"; do
    slug=$(basename "$dir")
    echo "  starting $slug"
    deploy_one "$dir" &
    pids+=($!)
  done

  for pid in "${pids[@]}"; do
    wait "$pid" || true
  done

  for dir in "${batch[@]}"; do
    slug=$(basename "$dir")
    result="$LOG_DIR/${slug}.result"
    if [ -f "$result" ]; then
      cat "$result" | sed 's/^/  /'
    else
      echo "  FAIL|$slug|no result"
    fi
  done
done

echo ""
echo "========== SUMMARY =========="
ok=0; partial=0; fail=0
for dir in "${RECIPES[@]}"; do
  slug=$(basename "$dir")
  result="$LOG_DIR/${slug}.result"
  if [ ! -f "$result" ]; then
    echo "FAIL|$slug|no result"
    fail=$((fail+1))
    continue
  fi
  line=$(cat "$result")
  echo "$line"
  if [[ "$line" == OK* ]]; then ok=$((ok+1))
  elif [[ "$line" == PARTIAL* ]]; then partial=$((partial+1))
  else fail=$((fail+1)); fi
done
echo "OK: $ok  PARTIAL: $partial  FAIL: $fail  TOTAL: $total"
echo "Logs: $LOG_DIR/"
