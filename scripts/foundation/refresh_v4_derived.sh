#!/usr/bin/env bash
# Nightly DERIVED rebuilds for the v4 surfaces — run AFTER the foundation lens refresh.
# All three steps are idempotent and safe to run even if upstream data is stale (they just
# re-derive from whatever is current), so wiring this into the nightly can't corrupt anything.
#
#   1. add_perf_indexes      — ensure the date indexes exist (they were dropped once by a table
#                              rebuild, which made every detail page seq-scan 3M rows / ~10s).
#   2. build_breadth_series  — rebuild the Nifty-500 breadth series (broad-trading days only).
#   3. build_fund_rank_history --latest — append today's per-fund category ranks (history table).
#
# Usage:  bash scripts/foundation/refresh_v4_derived.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
PY=python3   # system python (has the deps these scripts need); falls back to .venv if missing
command -v "$PY" >/dev/null 2>&1 || PY=.venv/bin/python

echo "=== refresh_v4_derived $(date -u +%FT%TZ) ==="
for step in \
  "scripts/foundation/add_perf_indexes.py" \
  "scripts/foundation/build_breadth_series.py" \
  "scripts/foundation/build_fund_rank_history.py --latest"; do
  echo "--- $step ---"
  # shellcheck disable=SC2086
  $PY $step || echo "!! $step failed (continuing)"
done
echo "=== refresh_v4_derived done ==="
