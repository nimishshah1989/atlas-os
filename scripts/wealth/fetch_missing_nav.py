"""Backfill NAV history for bridged client schemes missing from de_mf_nav_daily.

Hybrids / commodity FoFs / debt resolved via the AMFI+ISIN bridges have mstar_ids
and amfi_codes but no NAV series (the nightly ingest covers only universe funds).
Same sanctioned source and insert shape as scripts/foundation/ingest_nav.py
(mfapi.in, the AMFI NAV mirror), additive rows only.

Usage:
    .venv/bin/python scripts/wealth/fetch_missing_nav.py
"""

from __future__ import annotations

import datetime
import os
import sys
import time

import psycopg2
import requests
from psycopg2.extras import execute_values

MFAPI = "https://api.mfapi.in/mf"
SINCE = datetime.date.today() - datetime.timedelta(days=4 * 365)


def fetch_one(amfi_code: str, retries: int = 3) -> list[dict] | None:
    for a in range(retries):
        try:
            r = requests.get(f"{MFAPI}/{amfi_code}", timeout=25)
            if r.status_code == 200:
                data = r.json().get("data") or []
                if data:
                    return data
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.2 * (a + 1))
    return None


def main() -> int:
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("""
        select distinct s.mstar_id, s.amfi_code, s.display_name
        from wealth.schemes s
        where s.mstar_id is not null and s.amfi_code is not null
          and not exists (select 1 from atlas_foundation.de_mf_nav_daily n
                          where n.mstar_id = s.mstar_id)""")
    targets = cur.fetchall()
    print(f"{len(targets)} schemes need NAV history (4y window)")
    ok = miss = total_rows = 0
    for mstar_id, amfi_code, name in targets:
        data = fetch_one(amfi_code)
        if not data:
            miss += 1
            print(f"  MISS {name} ({amfi_code})")
            continue
        rows = []
        for d in data:  # mfapi rows: {"date":"18-07-2026","nav":"123.4567"}
            try:
                dt = datetime.datetime.strptime(d["date"], "%d-%m-%Y").date()
                nav = float(d["nav"])
            except (KeyError, ValueError):
                continue
            if dt >= SINCE and nav > 0:
                rows.append((dt, mstar_id, nav, "amfi_backfill"))
        if not rows:
            miss += 1
            continue
        execute_values(cur,
                       "insert into atlas_foundation.de_mf_nav_daily "
                       "(nav_date, mstar_id, nav, data_status) values %s "
                       "on conflict (nav_date, mstar_id) do nothing",
                       rows, page_size=5000)
        conn.commit()
        ok += 1
        total_rows += len(rows)
        time.sleep(0.25)
    print(f"DONE: {ok} schemes backfilled ({total_rows} rows), {miss} missed")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
