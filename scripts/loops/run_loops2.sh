#!/usr/bin/env bash
# Round 2 — fix + complete the data, then the ETF/index/sector roll-up.
# Loop A → Loop B (B depends on A's full-universe historical instrument scores).
# Each is one headless ultracode `claude -p` that runs until the INDEPENDENT gate
# (validate_lenses.py, which it may not edit) exits 0, then stops. Auto mode,
# bypass permissions, branch-isolated (feat/v4-six-lens), pushes for phone review.
set -uo pipefail
cd /home/ubuntu/atlas-os
FLAGS="--permission-mode bypassPermissions --model opus --output-format text"

run () {  # name  promptfile  budget_usd
  echo "===== [$(date -u)] START $1 (budget \$$3) ====="
  claude -p "$(cat "$2")" $FLAGS --max-budget-usd "$3" 2>&1 | tee "/tmp/$1.log"
  echo "===== [$(date -u)] END $1 (exit ${PIPESTATUS[0]}) ====="
}

run loopA_data    scripts/loops/loopA_data_complete.md  500
run loopB_rollup  scripts/loops/loopB_etf_sector.md     400
echo "===== [$(date -u)] ROUND 2 COMPLETE ====="
