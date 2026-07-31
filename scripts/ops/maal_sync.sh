#!/usr/bin/env bash
# MaaL book sync — pull BJ53 / BJ53IND / JR100PASS from the CPP database.
# Called twice a day by cron (see scripts/ops/crontab.txt): 12:00 and 22:00 IST.
#
# Twice, because positions in the portal only move when a backoffice file is
# uploaded: the noon run catches a morning upload, the 22:00 run catches an
# evening one. Neither invents a date — every row carries both when we looked
# (as_of) and when the data is actually from (source_as_of).
set -euo pipefail
REPO="/home/ubuntu/atlas-os"
cd "$REPO"
export PYTHONPATH="$REPO:$REPO/scripts/foundation"   # covers atlas.* and _db imports
set -a; source .env; set +a

"$REPO/.venv/bin/python" scripts/foundation/sync_maal_books.py

# P&L reconciliation: proves the FIFO numbers still hold as new trades land.
# Non-fatal — a reconciliation failure must not stop tomorrow's position sync,
# and the exit code above already gates the thing that matters.
"$REPO/.venv/bin/python" scripts/ops/maal_pnl_reconcile.py || true
