#!/bin/bash
# One-off resilient backfill of 07-01 EOD stock candles from Kite. The full-universe
# historical pull trips Kite's sustained-burst throttle (transient "invalid token"),
# so this loops the incremental pull (each pass re-fetches only stocks still behind)
# with cooldown pauses until coverage is complete. Delete after 07-01 is loaded.
set -uo pipefail
cd /home/ubuntu/atlas-os
export PYTHONPATH="$(pwd):$(pwd)/scripts/foundation"
set -a; source .env; set +a
PY=.venv/bin/python
TARGET=2000
LOG=/home/ubuntu/logs/kite_backfill_0701.log
echo "=== 07-01 stock backfill start $(date -Is) ===" | tee -a "$LOG"
for i in $(seq 1 40); do
  n=$($PY -c "import _db; print(_db.scalar(\"select count(*) from atlas_foundation.ohlcv_stock where date='2026-07-01'\"))")
  echo "[backfill] pass $i — stocks@07-01=$n/$TARGET $(date -Is)" | tee -a "$LOG"
  if [ "$n" -ge "$TARGET" ]; then echo "[backfill] COMPLETE" | tee -a "$LOG"; break; fi
  $PY scripts/foundation/ingest_kite.py --asset stock >> "$LOG" 2>&1 || true
  sleep 90
done
echo "=== 07-01 stock backfill end $(date -Is) ===" | tee -a "$LOG"
