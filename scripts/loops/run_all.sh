#!/usr/bin/env bash
# Chained autonomous build — data → calculation → frontend (they are DEPENDENT, so
# sequential, not parallel). Each is one headless `claude -p` ultracode session that
# runs to its gate and exits; the next starts only after the previous returns.
# Branch-isolated (feat/v4-six-lens), feature-flagged, gated, NO deploy/switch.
# Run detached in tmux; survives your laptop shutting. Logs per loop in /tmp.
set -uo pipefail
cd /home/ubuntu/atlas-os
FLAGS="--permission-mode bypassPermissions --model opus --output-format text"

run () {  # name  promptfile  budget_usd
  echo "===== [$(date -u)] START $1 (budget \$$3) ====="
  claude -p "$(cat "$2")" $FLAGS --max-budget-usd "$3" 2>&1 | tee "/tmp/$1.log"
  echo "===== [$(date -u)] END $1 (exit ${PIPESTATUS[0]}) ====="
}

run loop1_data     scripts/loops/loop1_data.md     300
run loop2_engine   scripts/loops/loop2_engine.md   800
run loop3_frontend scripts/loops/loop3_frontend.md 400
echo "===== [$(date -u)] ALL LOOPS COMPLETE ====="
