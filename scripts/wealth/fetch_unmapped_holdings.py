"""Fetch Morningstar holdings for client-held funds missing from the equity master.

The equity-only Morningstar master leaves hybrids / commodity FoFs / a few equity
funds without mstar_ids. The holdings service accepts ISIN selectors (verified),
and AMFI gave us ISINs for 99% of value — so per FM directive, every NON-DEBT
unmapped scheme gets its holdings pulled and its mstar_id resolved from the
response. Rows land in atlas_foundation.de_mf_holdings (same sanctioned boundary
+ table as ingest_mf_holdings.py, whose parser this reuses).

Usage:
    .venv/bin/python scripts/wealth/fetch_unmapped_holdings.py
"""

from __future__ import annotations

import datetime
import os
import sys
import time
import uuid

import psycopg2
import requests
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "foundation"))
# resolved at runtime via the sys.path insert above:
# pyright: reportMissingImports=false
from ingest_mf_holdings import parse_fund

MSTAR_BASE = "https://api.morningstar.com/v2/service/mf"


def fetch_by_isin(svc: str, ac: str, isin: str, retries: int = 3) -> bytes | None:
    url = f"{MSTAR_BASE}/{svc}/isin/{isin}?accesscode={ac}"
    for a in range(retries):
        try:
            r = requests.get(url, timeout=40)
            if r.status_code == 200 and r.content.rstrip().endswith(b"</response>"):
                return r.content
        except requests.RequestException:
            pass
        time.sleep(1.5 * (a + 1))
    return None


def main() -> int:
    svc = os.environ.get("MSTAR_HOLDINGS_SERVICE", "fq9mxhk7xeb20f3b")
    ac = os.environ["MSTAR_ACCESSCODE"]
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("""select s.scheme_id, s.display_name, s.isin, s.asset_class,
                          round(coalesce(sum(h.market_value), 0) / 1e7, 2) as mv_cr
                   from wealth.schemes s left join wealth.holdings h using (scheme_id)
                   where s.isin is not null and s.mstar_id is null and s.asset_class <> 'Debt'
                   group by 1, 2, 3, 4 order by 5 desc""")
    targets = cur.fetchall()
    print(f"{len(targets)} non-debt schemes need holdings (by ISIN)")

    cur.execute(
        "select isin, instrument_id from atlas_foundation.instrument_master "
        "where isin is not null and asset_class='stock'"
    )
    isin_map = dict(cur.fetchall())

    today = datetime.date.today()
    ok = miss = 0
    scheme_updates = []
    rows = []
    for scheme_id, display, isin, _cls, _mv in targets:
        xml = fetch_by_isin(svc, ac, isin)
        if not xml:
            miss += 1
            print(f"  MISS {display} ({isin})")
            continue
        fund_rows = list(parse_fund(xml))
        if not fund_rows:
            miss += 1
            print(f"  EMPTY {display} ({isin})")
            continue
        ok += 1
        mstar_id = fund_rows[0]["mstar_id"]
        scheme_updates.append((mstar_id, scheme_id))
        for h in fund_rows:
            iid = isin_map.get(h["isin"]) if h["isin"] else None
            rows.append(
                (
                    str(uuid.uuid4()),
                    mstar_id,
                    today,
                    h["holding_name"],
                    h["isin"],
                    iid,
                    h["weight_pct"],
                    h["shares_held"],
                    h["market_value"],
                    h["sector_code"],
                    iid is not None,
                )
            )
        time.sleep(0.3)

    new_ids = sorted({r[1] for r in rows})
    if rows:
        cur.execute(
            "delete from atlas_foundation.de_mf_holdings "
            "where as_of_date = %s and mstar_id = any(%s)",
            (today, new_ids),
        )
        execute_values(
            cur,
            "insert into atlas_foundation.de_mf_holdings "
            "(id, mstar_id, as_of_date, holding_name, isin, instrument_id, weight_pct,"
            " shares_held, market_value, sector_code, is_mapped) values %s",
            rows,
            page_size=5000,
        )
    if scheme_updates:
        cur.executemany(
            "update wealth.schemes set mstar_id = %s, match_method = 'isin_holdings' "
            "where scheme_id = %s",
            scheme_updates,
        )
    conn.commit()
    print(
        f"DONE: {ok} funds fetched, {miss} missed; {len(rows)} holding rows; "
        f"{len(scheme_updates)} schemes got mstar_ids"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
