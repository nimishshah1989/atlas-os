#!/usr/bin/env python3
"""Atlas-owned Morningstar ETF-holdings ingestion → atlas_foundation.de_etf_holdings.

Sibling of ingest_mf_holdings.py for the ETF universe. de_etf_holdings had NO
producer croned — it froze at 2026-05-04 (59d stale) while the /etfs + /funds
lens roll-ups (etf_lens.SCORED_STOCKS) and the sector free-float weights
(rollup_sectors._weights) kept reading it.

ETFs share the SAME Morningstar Fund-Holdings service as mutual funds, keyed by
mstar_id (F-code) — so this reuses fetch_one + parse_fund from ingest_mf_holdings
and just swaps the universe (de_mf_master where is_etf) and the target table.

de_etf_holdings is a lean look-through bridge: (ticker=mstar_id, instrument_id,
weight, as_of_date, last_disclosed_date). It carries only the equity holdings
that map to a scored NSE instrument (its consumers INNER-join on instrument_id),
so unmapped rows are dropped. weight is stored as a FRACTION (0.0428) — the
Morningstar "Weighting" percent ÷ 100, matching the existing rows and the scale
etf_lens/rollup_sectors expect. RULE #0: only real Morningstar holdings; an ETF
that returns nothing is skipped, never fabricated. Run WEEKLY (atlas_weekly.sh).
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import _db
from ingest_mf_holdings import WORKERS, fetch_one, parse_fund
from psycopg2.extras import execute_values


def main() -> None:
    # Route the connection through _db (SQLAlchemy) — it normalises the +psycopg2 URL that
    # raw psycopg2.connect can't parse, and is the same engine the rest of the pipeline uses.
    conn = _db.engine().raw_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT isin, instrument_id FROM atlas_foundation.instrument_master "
        "WHERE isin IS NOT NULL AND asset_class='stock'"
    )
    isin_map = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT DISTINCT mstar_id FROM atlas_foundation.de_mf_master WHERE is_etf")
    etfs = [r[0] for r in cur.fetchall() if r[0]]
    print(f"fetching holdings for {len(etfs)} ETFs @ {WORKERS} workers ...", flush=True)

    today = datetime.date.today()
    rows, ok, miss = [], 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, f): f for f in etfs}
        for i, fut in enumerate(as_completed(futs), 1):
            xml = fut.result()
            if not xml:
                miss += 1
                continue
            try:  # one malformed payload must not abort the whole refresh (matches mf ingest)
                holdings = list(parse_fund(xml))
            except ET.ParseError:
                miss += 1
                continue
            ok += 1
            for h in holdings:
                iid = isin_map.get(h["isin"]) if h["isin"] else None
                if iid is None or h["weight_pct"] is None:
                    continue  # look-through bridge keeps only mapped equity holdings
                rows.append((h["mstar_id"], iid, h["weight_pct"] / 100.0, today, today))
            if i % 50 == 0:
                print(f"  {i}/{len(etfs)} ...", flush=True)

    # de_etf_holdings is a SINGLE-SNAPSHOT current-holdings table: rollup_sectors._weights
    # reads it with NO date filter, so a second as_of_date would double-count a ticker. So
    # full-swap the whole table each run (also clears legacy .NS-keyed rows from the dead
    # ingest). SAFETY: never wipe on a thin fetch — a healthy run refreshes ~181/182 ETFs,
    # so abort the swap (rows kept intact) if fewer than MIN_ETFS came back.
    MIN_ETFS = 120
    refreshed = sorted({r[0] for r in rows})
    if len(refreshed) < MIN_ETFS:
        raise RuntimeError(
            f"only {len(refreshed)} ETFs returned holdings (< {MIN_ETFS}) — refusing to swap "
            f"de_etf_holdings (would blank the table); {ok} fetched / {miss} failed"
        )
    cur.execute("DELETE FROM atlas_foundation.de_etf_holdings")  # atomic swap: insert follows
    execute_values(
        cur,
        "INSERT INTO atlas_foundation.de_etf_holdings "
        "(ticker, instrument_id, weight, as_of_date, last_disclosed_date) VALUES %s",
        rows,
        page_size=5000,
    )
    conn.commit()
    print(
        f"DONE · {ok} ETFs fetched ({miss} failed) · {len(rows)} mapped holdings across "
        f"{len(refreshed)} ETFs · as_of {today}",
        flush=True,
    )
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
