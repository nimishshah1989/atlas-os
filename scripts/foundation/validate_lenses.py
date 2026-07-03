#!/usr/bin/env python3
"""INDEPENDENT lens-output gate — written by hand, NOT by the build loops.

This is the falsifiable, data-grounded definition of done. The loops must make the
REAL output satisfy these assertions; they are FORBIDDEN to edit this file to pass.
Each assertion queries the actual produced data (not unit tests on synthetic data) —
which is exactly what catches the class of bug the first build missed (catalyst = 0
for names with hundreds of filings; only 750/2000 scored; a single date).

    python validate_lenses.py --check A   # Loop A: instrument-level completeness+correctness
    python validate_lenses.py --check B   # Loop B: ETF/index/sector roll-up
Exit 0 iff every assertion passes. Prints PASS/FAIL per assertion.
"""

from __future__ import annotations

import argparse
import sys

import _db

# Single read schema: validate exactly what the platform serves (atlas_foundation).
L = "atlas_foundation.atlas_lens_scores_daily"
SEC = "atlas_foundation.sector_lens_daily"
IM = "atlas_foundation.instrument_master"
FILINGS = "atlas_foundation.lens_filings"
# Coverage universe = Atlas's active set (NIFTY 500 = 498, FM 2026-06-25). Completeness
# is measured against the universe we actually score, not every kite_token instrument.
ACTIVE = f"{IM} where asset_class='stock' and kite_token is not null and is_active"
LENSES = ["technical", "fundamental", "valuation", "catalyst", "flow", "policy"]


def _q(sql, p=None):
    return _db.scalar(sql, p)


class Gate:
    def __init__(self):
        self.fails = 0

    def check(self, name, ok, detail=""):
        tag = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        print(f"  [{tag}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            self.fails += 1
        return ok


# ─────────────────────────── LOOP A ───────────────────────────
def check_A(g: Gate):
    print("== Loop A gate: instrument-level completeness + correctness ==")
    n_uni = _q(f"select count(*) from {ACTIVE}")
    mx = _q(f"select max(date) from {L} where asset_class='stock'")
    g.check("latest date exists", mx is not None, str(mx))

    # 1. FULL coverage universe scored (≥95% of the active NIFTY 500), not 750
    n_scored = _q(
        f"select count(distinct instrument_id) from {L} where asset_class='stock' and date=:d",
        {"d": mx},
    )
    g.check("universe coverage ≥95%", n_scored >= 0.95 * n_uni, f"{n_scored}/{n_uni} stocks scored")

    # 2. CATALYST is grounded: filing-rich names IN COVERAGE (≥50 filings) must mostly
    #    score >0 — the original bug was catalyst=0 for names with hundreds of filings.
    rich = _q(f"""
        with f as (select instrument_id, count(*) c from {FILINGS}
                   where instrument_id in (select instrument_id from {ACTIVE})
                   group by 1 having count(*) >= 50)
        select count(*) from f""")
    rich_pos = _q(
        f"""
        with f as (select instrument_id, count(*) c from {FILINGS}
                   where instrument_id in (select instrument_id from {ACTIVE})
                   group by 1 having count(*) >= 50)
        select count(*) from f join {L} l on l.instrument_id=f.instrument_id and l.date=:d
        where l.catalyst > 0""",
        {"d": mx},
    )
    frac = (rich_pos / rich) if rich else 0
    g.check(
        "catalyst grounded (filing-rich names score >0)",
        frac >= 0.60,
        f"{rich_pos}/{rich} filing-rich names have catalyst>0 ({frac:.0%})",
    )

    # 3. FLOW non-degenerate (not all ~12) and meaningfully populated
    fstd = _q(f"select stddev(flow) from {L} where asset_class='stock' and date=:d", {"d": mx}) or 0
    fpos = _q(
        f"select count(*) from {L} where asset_class='stock' and date=:d and flow>0", {"d": mx}
    )
    g.check(
        "flow non-degenerate",
        float(fstd) >= 5 and fpos >= 0.40 * n_scored,
        f"stddev={float(fstd):.1f}, {fpos} names flow>0",
    )

    # 4. Every lens populated for ≥80% of scored instruments
    for lens in LENSES:
        nn = _q(
            f"select count(*) from {L} where asset_class='stock' and date=:d and {lens} is not null",
            {"d": mx},
        )
        g.check(f"{lens} coverage ≥80%", nn >= 0.80 * n_scored, f"{nn}/{n_scored}")

    # 5. HISTORICAL journal exists (not a single date): many dates + deep per-instrument history
    ndates = _q(f"select count(distinct date) from {L} where asset_class='stock'")
    g.check("historical journal ≥250 dates", ndates >= 250, f"{ndates} distinct dates")
    deep = _q(f"""select count(*) from (
        select instrument_id, count(*) c from {L} where asset_class='stock' group by 1 having count(*) >= 250
    ) t""")
    g.check(
        "≥80% instruments have ≥250 historical dates",
        deep >= 0.80 * n_uni,
        f"{deep} instruments deep",
    )


# ─────────────────────────── LOOP B ───────────────────────────
def check_B(g: Gate):
    """Validate what the lens pipeline actually PRODUCES: the sector roll-up + the
    scored-universe sector mapping. (The lens journal is stocks-only by design —
    ETFs are scored as a native holdings-weighted roll-up of the stock atom (etf_lens),
    and indices are benchmarks, not lens entities — so the old 'ETF/index lens coverage'
    checks were architecturally void and are removed here.)"""
    print("== Loop B gate: sector roll-up + scored-universe mapping ==")

    # Sector roll-up table exists + every actionable sector has a vector
    sec_n = _q(f"select count(distinct sector) from {SEC}") or 0
    g.check("sector lens vectors exist (≥20 sectors)", sec_n >= 20, f"{sec_n} sectors")

    # Mapping completeness: every SCORED stock (the active NIFTY-500 universe) has a
    # sector. ETFs/indices carry no equity 'sector' and are correctly excluded.
    unmapped = _q(f"""select count(*) from {IM}
        where asset_class='stock' and kite_token is not null and is_active
          and (sector is null or sector='')""")
    g.check(
        "scored-universe sector mapping complete",
        unmapped == 0,
        f"{unmapped} active stocks unmapped",
    )

    # Roll-up sanity: a sector score must lie in the valid 0-100 range.
    bad = _q(f"""
        with latest as (select max(date) d from {SEC})
        select count(*) from {SEC} s, latest
        where s.date=latest.d and (s.technical < 0 or s.technical > 100)""")
    g.check("sector scores in valid 0-100 range", bad == 0, f"{bad} out-of-range")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", choices=["A", "B"], required=True)
    args = ap.parse_args()
    g = Gate()
    try:
        (check_A if args.check == "A" else check_B)(g)
    except Exception as e:
        print(f"  \033[31mFAIL\033[0m gate raised: {e!r}")
        g.fails += 1
    print(f"\n{'✅ ALL GREEN' if g.fails == 0 else f'❌ {g.fails} assertion(s) FAILED'}")
    sys.exit(0 if g.fails == 0 else 1)


if __name__ == "__main__":
    main()
