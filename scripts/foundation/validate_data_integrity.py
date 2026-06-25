#!/usr/bin/env python3
"""Data-integrity gate — the checks the first build MISSED, asserted on REAL rows.

Companion to validate_lenses.py. Loop A/B check completeness + roll-up; this checks
the failure classes the FM hit: STALE data, PLACEHOLDER sub-scores (collapsed to a
handful of values), the sector-breadth EMA21/200 omission, INSANE MV returns, the
368 unmapped instruments, and the un-folded sector taxonomy (D13).

Same rule as the lens gate: it is the falsifiable definition of done. Do NOT edit it
to pass — make the pipeline produce data that satisfies it.

    python validate_data_integrity.py
Exit 0 iff every assertion passes.
"""
from __future__ import annotations

import datetime
import sys

import _db


def _q(sql, p=None):
    return _db.scalar(sql, p)


LD = "atlas.atlas_lens_scores_daily"
MVB = "foundation_staging.mv_sector_breadth"
MVC = "foundation_staging.mv_sector_cards"
IM = "foundation_staging.instrument_master"


class Gate:
    def __init__(self):
        self.fails = 0

    def check(self, name, ok, detail=""):
        tag = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        print(f"  [{tag}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            self.fails += 1
        return ok


def _col_exists(schema, table, col):
    return bool(_q(
        "select count(*) from information_schema.columns "
        "where table_schema=:s and table_name=:t and column_name=:c",
        {"s": schema, "t": table, "c": col}))


def main():
    g = Gate()
    today = datetime.date.today()

    def days_old(d):
        return (today - d).days if d else 999

    print("== Data-integrity gate (freshness · real sub-scores · breadth EMA21 · returns · mapping · taxonomy) ==")

    # 1 — FRESHNESS (nothing stale; lens journal current with the technicals)
    lens_d = _q(f"select max(date) from {LD} where asset_class='stock'")
    tech_d = _q("select max(date) from foundation_staging.technical_daily where asset_class='stock'")
    mvb_d = _q(f"select max(as_of_date) from {MVB}")
    g.check("technicals fresh (≤4 days old)", days_old(tech_d) <= 4, f"technical_daily={tech_d}, today={today}")
    g.check("lens journal current with technicals", lens_d == tech_d, f"lens={lens_d} tech={tech_d}")
    g.check("sector MVs fresh (≤4 days old)", days_old(mvb_d) <= 4, f"mv_sector_breadth={mvb_d}")

    # 2 — REAL sub-scores (the placeholders collapse to 5-9 distinct values across 2,093 stocks)
    for col, floor in [("fund_profitability", 50), ("val_pe_vs_sector", 50), ("flow_institutional", 50), ("policy_tailwind", 30)]:
        nd = _q(f"select count(distinct {col}) from {LD} where asset_class='stock' and date=:d", {"d": lens_d})
        g.check(f"{col} real (>{floor} distinct)", (nd or 0) > floor, f"{nd} distinct")

    # 3 — SECTOR BREADTH EMA21 + EMA200 populated at the latest date
    has21 = _col_exists("foundation_staging", "mv_sector_breadth", "pct_above_ema21")
    g.check("breadth uses EMA21 column (not EMA20)", has21, "pct_above_ema21 present" if has21 else "still pct_above_ema20")
    bcol = "pct_above_ema21" if has21 else "pct_above_ema20"
    if mvb_d:
        tot = _q(f"select count(*) from {MVB} where as_of_date=:d", {"d": mvb_d})
        nn21 = _q(f"select count({bcol}) from {MVB} where as_of_date=:d", {"d": mvb_d})
        nn200 = _q(f"select count(pct_above_ema200) from {MVB} where as_of_date=:d", {"d": mvb_d})
        g.check("breadth EMA21 populated (latest)", bool(tot) and nn21 >= 0.95 * tot, f"{nn21}/{tot}")
        g.check("breadth EMA200 populated (latest)", bool(tot) and nn200 >= 0.95 * tot, f"{nn200}/{tot}")

    # 4 — MV RETURNS sane + ret_12m present (Defence ret_6m showed +111%)
    mvc_d = _q(f"select max(as_of_date) from {MVC}")
    if mvc_d:
        bad = _q(f"select count(*) from {MVC} where as_of_date=:d and (abs(ret_6m)>0.8 or abs(ret_3m)>0.6)", {"d": mvc_d})
        g.check("sector returns in sane range (|6m|≤80%)", bad == 0, f"{bad} sectors out of range")
        null12 = _q(f"select count(*) from {MVC} where as_of_date=:d and ret_12m is null", {"d": mvc_d})
        g.check("ret_12m populated for all sectors", null12 == 0, f"{null12} null ret_12m")

    # 5 — SECTOR MAPPING complete (the 368 unmapped)
    unmapped = _q(f"select count(*) from {IM} where asset_class='stock' and is_active and (sector is null or sector='')")
    g.check("every active stock has a sector", unmapped == 0, f"{unmapped} unmapped")

    # 6 — TAXONOMY folded to canonical actionable sectors (D13, 29→21)
    has_rollup = bool(_q("select count(*) from information_schema.tables where table_name='atlas_sector_rollup'"))
    g.check("sector rollup table exists (D13 fold)", has_rollup, "atlas_sector_rollup")
    nsec = _q(f"select count(distinct sector) from {IM} where asset_class='stock' and sector is not null and sector<>''")
    g.check("≤21 canonical sectors (folded)", (nsec or 99) <= 21, f"{nsec} distinct sectors")

    print(f"\n{'✅ ALL GREEN' if g.fails == 0 else f'❌ {g.fails} assertion(s) FAILED'}")
    sys.exit(0 if g.fails == 0 else 1)


if __name__ == "__main__":
    main()
