#!/usr/bin/env python3
"""The 5-minute worker: book and mark every NEW basket, so a basket built on the board shows
its first NAV within minutes rather than after the next nightly.

    */5 * * * *  flock -n /tmp/atlas_global_baskets.lock /home/ubuntu/atlas-os/.venv/bin/python \\
                 /home/ubuntu/atlas-os/scripts/global_market/basket_job_worker.py \\
                 >> /home/ubuntu/logs/basket_job_worker.log 2>&1

WHY A WORKER AND NOT THE ROUTE. The board's create action writes ``basket_master`` and
``basket_constituents`` and nothing else — no Python is spawned from a Next.js handler
(CLAUDE.md, "Boards read Postgres directly"), and the accounting must not live in two places.
So a new basket is exactly "an active basket with no live NAV row", and this script hands
that set to ``mark_baskets.run(only_new=True)`` — the same code path the nightly takes, with
the same thresholds, prices and engine. Nothing here books; nothing here has a second opinion.

WHAT IT PRINTS. Nothing at all when there is nothing to do — this runs 288 times a day, and
a log that says "idle" every five minutes buries the lines that matter. A basket it booked
prints ``mark_baskets``' own summary line; a refusal prints ``REFUSED`` with the reason and
exits 1, and the basket stays unmarked (its page says so) until the constituents are fixed.

LOCKS. ``flock -n`` on its OWN lock file only stops two workers overlapping; it deliberately
does not take the nightly's ``/tmp/atlas_global.lock`` (a worker holding that at 01:00 UTC
would skip the whole night's run). Meeting the nightly on the same basket is safe instead:
``mark_baskets.write_inception`` locks the basket row and re-checks for trades inside one
transaction, and the NAV upsert is idempotent.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, basket_data, mark_baskets
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package
import _gdb
import basket_data as data
import mark_baskets


def main() -> int:
    if not data.unmarked_basket_ids():
        return 0  # idle: say nothing (288 runs a day)
    eod = _gdb.eod_cutoff()
    print(f"[basket_job_worker] {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')} EOD={eod}")
    return mark_baskets.run(eod, basket_ids=None, only_new=True, dry_run=False, report=None)


if __name__ == "__main__":
    sys.exit(main())
