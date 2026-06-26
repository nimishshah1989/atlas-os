#!/usr/bin/env python3
"""Atlas-owned MF NAV ingestion → foundation_staging.de_mf_nav_daily (single-schema).

Step 2 of the data consolidation. Replaces the JIP-RDS NAV sync (jip_incremental_sync.py
copied de_mf_nav_daily out of the external data-engine) AND the JIP-coupled stuck-funds
patch (amfi_nav_backfill.py looked AMFI codes up in the JIP RDS). Both are killed by this.

Source = mfapi.in (the free AMFI NAV mirror). The mstar_id -> amfi_code map now comes from
foundation_staging.de_mf_master (refreshed by ingest_fund_master.py from Morningstar), so
there is NO external-DB dependency at all. Incremental by default: per fund, fetch only NAVs
newer than the latest already stored. Idempotent (ON CONFLICT DO NOTHING). Parallel.

Config from env:  ATLAS_DB_URL  (NAV_WORKERS optional, default 8)

Run:  python ingest_nav.py             # incremental refresh (universe funds)
      python ingest_nav.py --full      # ignore last-stored date, re-pull full history
      python ingest_nav.py --dry-run   # fetch + parse + report, no writes
"""

from __future__ import annotations

import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import requests
from psycopg2.extras import execute_values

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except Exception:
    pass

DB = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
WORKERS = int(os.environ.get("NAV_WORKERS", "8"))
MFAPI = "https://api.mfapi.in/mf"


def fetch_one(amfi_code: int, retries: int = 3) -> list[dict] | None:
    for _a in range(retries):
        try:
            r = requests.get(f"{MFAPI}/{amfi_code}", timeout=25)
            if r.status_code == 200:
                return r.json().get("data", []) or []
        except (requests.RequestException, ValueError):
            pass
    return None


def _d(s: str):
    try:
        return datetime.datetime.strptime(s, "%d-%m-%Y").date()
    except (TypeError, ValueError):
        return None


def main() -> None:
    full = "--full" in sys.argv
    dry = "--dry-run" in sys.argv
    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    # Take clean ownership: a unique key on (nav_date, mstar_id) for idempotent upsert.
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_de_mf_nav_daily_date_mstar "
        "ON foundation_staging.de_mf_nav_daily (nav_date, mstar_id)"
    )
    conn.commit()

    cur.execute(
        "SELECT u.mstar_id, m.amfi_code "
        "FROM foundation_staging.atlas_universe_funds u "
        "JOIN foundation_staging.de_mf_master m ON m.mstar_id = u.mstar_id "
        "WHERE m.amfi_code IS NOT NULL"
    )
    funds = [(r[0], int(r[1])) for r in cur.fetchall()]
    last: dict[str, datetime.date] = {}
    if not full:
        cur.execute(
            "SELECT mstar_id, max(nav_date) FROM foundation_staging.de_mf_nav_daily "
            "GROUP BY mstar_id"
        )
        last = {r[0]: r[1] for r in cur.fetchall()}
    print(
        f"NAV ingest: {len(funds)} funds @ {WORKERS} workers · {'FULL' if full else 'incremental'}",
        flush=True,
    )

    rows, ok, miss = [], 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, ac): (mid, ac) for mid, ac in funds}
        for i, fut in enumerate(as_completed(futs), 1):
            mid, _ = futs[fut]
            data = fut.result()
            if data is None:
                miss += 1
                continue
            ok += 1
            cutoff = last.get(mid)
            for item in data:
                d = _d(item.get("date", ""))
                nav = item.get("nav")
                if d is None or nav in (None, "", "0", "0.00000"):
                    continue
                if cutoff is not None and d <= cutoff:
                    continue
                try:
                    nav_f = float(nav)
                except (TypeError, ValueError):
                    continue
                rows.append((d, mid, nav_f, "raw"))
            if i % 100 == 0:
                print(f"  {i}/{len(funds)} ... ({len(rows)} new rows so far)", flush=True)

    print(f"fetched {ok} funds ({miss} failed) · {len(rows)} new NAV rows", flush=True)
    if dry:
        print("DRY RUN — no writes")
        cur.close()
        conn.close()
        return

    if rows:
        execute_values(
            cur,
            "INSERT INTO foundation_staging.de_mf_nav_daily "
            "(nav_date, mstar_id, nav, data_status) VALUES %s "
            "ON CONFLICT (nav_date, mstar_id) DO NOTHING",
            rows,
            page_size=5000,
        )
        conn.commit()
    mx = None
    cur.execute("SELECT max(nav_date) FROM foundation_staging.de_mf_nav_daily")
    mx = cur.fetchone()[0]
    print(f"DONE · {len(rows)} candidate rows · max nav_date now {mx}", flush=True)
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
