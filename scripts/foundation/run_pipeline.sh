#!/usr/bin/env bash
# Autonomous tail of the foundation build: once the backfill finishes, compute
# all technicals, then validate the full universe. Each step is resumable, so a
# restart picks up where it left off. Logs to /tmp/{compute,validate}.log.
set -uo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
export $(grep -E '^(KITE_|ATLAS_)' .env 2>/dev/null | xargs) 2>/dev/null || true

echo "[pipeline] waiting for backfill to finish…"
until grep -qE 'COMPLETE|AUTH FAILURE' /tmp/backfill.log 2>/dev/null; do sleep 30; done
echo "[pipeline] backfill ended; starting parallel compute (7 workers across 8 cores)"

# CPU-bound TA-Lib compute parallelised across cores via stable disjoint shards.
N=7
pids=()
for k in $(seq 0 $((N-1))); do
  $PY -c "
from dotenv import load_dotenv; load_dotenv('.env')
import sys; sys.path.insert(0,'scripts/foundation')
import compute_all; compute_all.run(shard=($k,$N))
" > /tmp/compute_$k.log 2>&1 &
  pids+=($!)
done
echo "[pipeline] compute workers: ${pids[*]}"
wait "${pids[@]}"
cat /tmp/compute_*.log | grep COMPLETE
echo "[pipeline] compute done; starting validate"

$PY -c "
from dotenv import load_dotenv; load_dotenv('.env')
import sys; sys.path.insert(0,'scripts/foundation')
import validate
[validate.run(ac) for ac in ('stock','etf','index')]
" > /tmp/validate.log 2>&1
echo "[pipeline] COMPLETE"
