#!/usr/bin/env python3
"""INDEPENDENT lens-output gate — written by hand, NOT by the build loops.

This is the falsifiable, data-grounded definition of done. The loops must make the
REAL output satisfy these assertions; they are FORBIDDEN to edit this file to pass.
Each assertion queries the actual produced data (not unit tests on synthetic data) —
which is exactly what catches the class of bug the first build missed (catalyst = 0
for names with hundreds of filings; only 750/2000 scored; a single date).

    python validate_lenses.py --check A   # Loop A: instrument-level completeness+correctness
    python validate_lenses.py --check B   # Loop B: ETF/index/sector roll-up
    python validate_lenses.py --check C   # Loop C: scoring-MATH correctness (wrong-number guards)
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


# ─────────────────────────── LOOP C ───────────────────────────
def check_C(g: Gate):
    """Scoring-MATH correctness — the invariants that catch a WRONG number, not just a
    missing/stale one (checks A/B cover coverage + staleness). Every assertion here is a
    structural property that must hold on real produced output; each guards a class of bug
    this system has actually shipped (unit/row-offset returns, inflated sector returns,
    a collapsed lens/composite, a mis-joined decile driving the leader flag)."""
    print("== Loop C gate: scoring-math correctness (wrong-number guards) ==")
    mx = _q(f"select max(date) from {L} where asset_class='stock'")

    # 1. Composite is on its 0-100 scale — nothing out of range.
    oob = _q(
        f"select count(*) from {L} where asset_class='stock' and date=:d and (composite<0 or composite>100)",
        {"d": mx},
    )
    g.check("composite in [0,100]", oob == 0, f"{oob} out-of-range")

    # 2. Composite is NOT degenerate (a broken blend collapses the spread). Baseline stddev ~33.
    csd = float(
        _q(f"select stddev(composite) from {L} where asset_class='stock' and date=:d", {"d": mx})
        or 0
    )
    g.check("composite non-degenerate (stddev>=10)", csd >= 10, f"stddev={csd:.1f}")

    # 3. EVERY lens sub-score has real spread (a lens producing a constant = a broken feed,
    #    the exact shape of the catalyst=0 incident). Conservative floor of 2.
    for lens in LENSES:
        sd = float(
            _q(f"select stddev({lens}) from {L} where asset_class='stock' and date=:d", {"d": mx})
            or 0
        )
        g.check(f"{lens} non-degenerate (stddev>=2)", sd >= 2, f"stddev={sd:.1f}")

    # 4. Decile within cap cohort is MONOTONE in composite — proves the decile that drives
    #    the leader flag is actually computed from composite, not stale / mis-joined.
    dviol = _q(
        f"""
        with cap as (select instrument_id,
            case when bool_or(index_code='NIFTY 100') then 'large'
                 when bool_or(index_code='NIFTY MIDCAP 150') then 'mid'
                 when bool_or(index_code='NIFTY SMLCAP 250') then 'small' else 'micro' end cap
          from atlas_foundation.de_index_constituents where effective_to is null
            and index_code in ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250') group by 1),
        dec as (select l.composite, coalesce(c.cap,'micro') cap,
            ntile(10) over (partition by coalesce(c.cap,'micro') order by l.composite) d
          from {L} l left join cap c on c.instrument_id=l.instrument_id
          where l.asset_class='stock' and l.date=:d and l.composite is not null),
        band as (select cap,d,min(composite) mn,max(composite) mx from dec group by cap,d)
        select count(*) from band b join band b2 on b2.cap=b.cap and b2.d=b.d+1 where b.mx>b2.mn+0.001""",
        {"d": mx},
    )
    g.check("decile monotone in composite (per cap cohort)", dviol == 0, f"{dviol} inversions")

    # 5. Daily returns are SANE — a unit bug (percent stored as fraction) yields |ret_1d|>>1.
    #    Real single-day moves stay well under 100%; anything above is a defect, not a mover.
    td = _q("select max(date) from atlas_foundation.technical_daily where asset_class='stock'")
    absurd = _q(
        "select count(*) from atlas_foundation.technical_daily where asset_class='stock' and date=:d and abs(ret_1d)>1.0",
        {"d": td},
    )
    g.check("ret_1d within sane bounds (|ret_1d|<=100%)", absurd == 0, f"{absurd} absurd returns")

    # 6. Sector-card returns MUST equal the sector index returns they're built from — guards
    #    the 2-5x-inflated bottom-up reconstruction from ever coming back (build_sector_cards).
    n_sec = _q(
        "select count(*) from atlas_foundation.mv_sector_cards where as_of_date=(select max(as_of_date) from atlas_foundation.mv_sector_cards)"
    )
    g.check("sector cards present (>=21)", (n_sec or 0) >= 21, f"{n_sec} sectors")
    smism = _q("""
        select count(*) from atlas_foundation.mv_sector_cards c
        join atlas_foundation.atlas_sector_master sm on sm.sector_name=c.sector_name
        join atlas_foundation.atlas_index_metrics_daily im on im.index_code=sm.primary_nse_index
          and im.date=(select max(date) from atlas_foundation.atlas_index_metrics_daily)
        where c.as_of_date=(select max(as_of_date) from atlas_foundation.mv_sector_cards)
          and c.ret_3m is not null and im.ret_3m is not null and abs(c.ret_3m-im.ret_3m)>0.0005""")
    g.check("sector-card returns match index metrics", smism == 0, f"{smism} mismatched sectors")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", choices=["A", "B", "C"], required=True)
    args = ap.parse_args()
    g = Gate()
    checks = {"A": check_A, "B": check_B, "C": check_C}
    try:
        checks[args.check](g)
    except Exception as e:
        print(f"  \033[31mFAIL\033[0m gate raised: {e!r}")
        g.fails += 1
    print(f"\n{'✅ ALL GREEN' if g.fails == 0 else f'❌ {g.fails} assertion(s) FAILED'}")
    sys.exit(0 if g.fails == 0 else 1)


if __name__ == "__main__":
    main()
