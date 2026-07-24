#!/usr/bin/env bash
# One-command refresh: engines → packs → narration → app → validate.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a
PY=.venv/bin/python

for s in build_overlap build_label_check build_tax_harvest build_value_statement \
         build_call_lists build_household build_audit_packs; do
  echo "== $s"
  $PY scripts/wealth/$s.py
done

$PY scripts/wealth/narrate_audit_packs.py "$@"
$PY scripts/wealth/build_capability_app.py
$PY scripts/wealth/validate_wealth_app.py

echo "READY: /home/ubuntu/jhaveri_data/reports/jhaveri-capability-app.html"
