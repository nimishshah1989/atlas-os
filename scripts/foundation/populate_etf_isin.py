#!/usr/bin/env python3
"""Populate foundation_staging.instrument_master.isin for NSE ETF rows (FM ask: complete the
instrument-master identity so ETF/fund equity look-through is robust).

Stock rows already carry ISIN; ETF rows did not. The authoritative ETF ISIN lives only on the
Morningstar side (de_mf_master.isin), so we fill instrument_master.isin for ETFs by a DETERMINISTIC
normalized-name join (UPPER + strip-non-alnum) de_mf_master.fund_name ⇄ instrument_master.name.
Additive (only fills NULL), idempotent. Non-matching ETFs keep NULL (RULE #0 — no fabrication;
their authoritative NSE ISIN would need an NSE securities-master fetch).

Note: the holdings look-through itself is already ~100% via instrument_id (de_mf_holdings 99.7%,
de_etf_holdings 99.5%); this is identity completeness, not a look-through fix.
"""

from __future__ import annotations

import _db


def main() -> None:
    before = _db.scalar(
        "SELECT count(*) FROM foundation_staging.instrument_master "
        "WHERE asset_class='etf' AND isin IS NOT NULL"
    )
    _db.exec_sql("""
      UPDATE foundation_staging.instrument_master im SET isin = sub.isin
      FROM (
        SELECT im2.instrument_id, min(mm.isin) AS isin
        FROM foundation_staging.instrument_master im2
        JOIN foundation_staging.de_mf_master mm
          ON mm.is_etf AND upper(regexp_replace(mm.fund_name,'[^A-Za-z0-9]','','g'))
                        = upper(regexp_replace(im2.name,'[^A-Za-z0-9]','','g'))
        WHERE im2.asset_class='etf'
        GROUP BY im2.instrument_id
      ) sub
      WHERE im.instrument_id = sub.instrument_id AND im.isin IS NULL""")
    after = _db.scalar(
        "SELECT count(*) FROM foundation_staging.instrument_master "
        "WHERE asset_class='etf' AND isin IS NOT NULL"
    )
    total = _db.scalar(
        "SELECT count(*) FROM foundation_staging.instrument_master WHERE asset_class='etf'"
    )
    print(f"instrument_master ETF isin: {before} -> {after} of {total} rows")


if __name__ == "__main__":
    main()
