#!/usr/bin/env python
"""Live intraday sector-RS builder — runs every 5 min during market hours.

Resolves each active sector's NSE-index kite_token + NIFTY 50, pulls one batched
kite.quote(), and writes (sector_name, ts, ratio = sector_ltp / nifty_ltp) into
atlas_foundation.atlas_sector_rs_intraday. Today-only retention (prunes pre-today
IST rows each run). Feeds the live tail on the sector RS ratio chart.

Bonus intraday table — deliberately NOT in the EOD freshness guard / producer
registry: it is legitimately empty overnight and runs on its own */5 market-hours
cron (not the daily orchestrator). freshness_guard guards EOD board tables only;
adding this would false-alarm every night.

ponytail: cron is market-hours-gated, so a stale pre-open/post-close tick can't be
written; no extra quote-timestamp freshness check needed. Add one if the cron ever
widens past the session.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import _db  # scripts/foundation local DB helper
import pandas as pd

from atlas.intraday import sector_rs as srs
from atlas.intraday.auth import get_valid_access_token


def _kite():
    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
    kite.set_access_token(get_valid_access_token(conn_str=_db.db_url()))
    return kite


def _resolve() -> tuple[list[srs.SectorTarget], int]:
    df = _db.read_df(srs.RESOLVE_TARGETS_SQL)
    targets = [
        srs.SectorTarget(str(sector), int(token))
        for sector, token in zip(df["sector_name"], df["index_token"], strict=False)
    ]
    nifty = _db.scalar(srs.NIFTY_INDEX_SQL)
    if nifty is None:
        raise SystemExit("NIFTY 50 kite_token not found in instrument_master")
    return targets, int(nifty)


def run() -> int:
    _db.exec_sql(srs.CREATE_TABLE_SQL)
    targets, nifty_token = _resolve()
    tokens = [t.index_token for t in targets] + [nifty_token]

    last_price: dict[int, float] = {}
    for key, quote in _kite().quote(tokens).items():  # kite keys come back as str(token)
        if not isinstance(quote, dict):
            continue
        try:
            last_price[int(str(key).split(":")[-1])] = float(quote["last_price"])
        except (KeyError, ValueError, TypeError):
            continue

    rows = srs.compute_ratios(last_price, targets, nifty_token)
    if not rows:
        print("no live quotes (market closed or empty tick) — nothing written")
        return 0

    ts = dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
    df = pd.DataFrame(
        {
            "sector_name": [s for s, _ in rows],
            "ts": [ts] * len(rows),
            "ratio": [r for _, r in rows],
        }
    )

    _db.exec_sql(srs.PRUNE_SQL)
    n = _db.upsert_df("atlas_foundation.atlas_sector_rs_intraday", df, ["sector_name", "ts"])
    print(f"wrote {n} intraday sector-RS rows @ {ts.isoformat()}")
    return n


if __name__ == "__main__":
    sys.exit(0 if run() >= 0 else 1)
