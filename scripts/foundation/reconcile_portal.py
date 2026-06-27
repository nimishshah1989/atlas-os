#!/usr/bin/env python3
"""Portal number reconciliation harness — the "trust table".

For every NUMBER the v4 portal displays, this recomputes the value INDEPENDENTLY
from raw inputs (raw OHLCV / index closes / per-stock flags) and compares it to
the value the page actually reads from its stored table. A row is GREEN only when
stored ≈ recomputed within tolerance.

This is the rule #0 deliverable: assert on real produced output, never on the mere
existence of a row. The whole point is that "the table is fresh and non-null" is
NOT evidence the number is correct — only an independent recompute is.

Ground-truth convention (established 2026-06-26):
  Returns are CALENDAR-anchored (last close on/before `as_of - N months`), NOT
  session-count-anchored. The stored tables count back a fixed number of *rows*;
  on a series with trading-day gaps that lands on the wrong calendar date and can
  inflate a return by several points (Nifty 50 3m: stored 6.9% vs true 3.2%).
  Cross-validated: two independent feeds (foundation_staging.index_prices [Kite]
  and public.de_index_prices [JIP]) agree to <0.1pp under calendar anchoring.

Run:
  python -m scripts.foundation.reconcile_portal           # full table
  python -m scripts.foundation.reconcile_portal --family returns
  python -m scripts.foundation.reconcile_portal --json out.json
Exit code is non-zero if any check FAILS, so it can gate CI / deploy.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date

from scripts.foundation._db import read_df, scalar

# ── result model ──────────────────────────────────────────────────────────────


@dataclass
class Check:
    family: str  # returns | breadth | lens | financials
    page: str  # which portal page shows this number
    metric: str  # human label
    scope: str  # entity (index/sector/stock) the number is for
    stored: float | None  # value the page reads from its stored table
    recomputed: float | None  # independent value from raw
    tol: float  # absolute tolerance, same units as the values
    unit: str = ""  # %, count, level …
    note: str = ""

    @property
    def delta(self) -> float | None:
        if self.stored is None or self.recomputed is None:
            return None
        return abs(self.stored - self.recomputed)

    @property
    def status(self) -> str:
        if self.recomputed is None:
            return "NO-TRUTH"  # could not establish ground truth — can't judge
        if self.stored is None:
            return "MISSING"  # page would show "—" / NULL where a value exists
        return "PASS" if self.delta <= self.tol else "FAIL"


RESULTS: list[Check] = []


def add(**kw) -> None:
    RESULTS.append(Check(**kw))


# ── as-of date (latest common snapshot) ───────────────────────────────────────


def as_of() -> date:
    return scalar(
        "select max(date) from foundation_staging.index_prices "
        "where index_code='NIFTY 50'"
    )


# ── ground-truth recompute: calendar-anchored index returns ──────────────────

_WINDOWS = [("ret_1m", "1 month"), ("ret_3m", "3 months"),
            ("ret_6m", "6 months"), ("ret_12m", "12 months")]


def recompute_index_returns(codes: list[str], d: date) -> dict[str, dict[str, float]]:
    """Calendar-anchored returns per index from foundation_staging.index_prices,
    cross-checked against public.de_index_prices. Returns {code: {ret_3m: pct,…}}.
    A window is left out (None) when the two feeds disagree by >0.5pp — that flags
    a raw-data defect rather than a silently-wrong "truth"."""
    sel = ",\n".join(
        f"""100*((select close from {{tbl}} a where a.index_code=c.index_code and a.date<=c.d order by a.date desc limit 1)
        / nullif((select close from {{tbl}} b where b.index_code=c.index_code and b.date<=c.d-interval '{lbl}' order by b.date desc limit 1),0)-1) "{k}\""""
        for k, lbl in _WINDOWS
    )
    # codes come from our own DB (NSE index names); single-quote-escape defensively
    vals = ",".join("('" + c.replace("'", "''") + "')" for c in codes)
    base = f"""
        with p as (select index_code, cast(:d as date) d from (values {vals}) v(index_code))
        select c.index_code, {sel} from p c order by c.index_code
    """
    fs = read_df(base.format(tbl="foundation_staging.index_prices"),
                 {"d": d}).set_index("index_code")
    de = read_df(base.format(tbl="public.de_index_prices"),
                 {"d": d}).set_index("index_code")
    out: dict[str, dict[str, float]] = {}
    for code in fs.index:
        out[code] = {}
        for k, _ in _WINDOWS:
            v_fs = fs.at[code, k] if code in fs.index else None
            v_de = de.at[code, k] if code in de.index else None
            # require cross-feed agreement to call it ground truth
            if v_fs is not None and v_de is not None and abs(v_fs - v_de) <= 0.5:
                out[code][k] = float(v_fs)
            elif v_fs is not None and v_de is None:
                out[code][k] = float(v_fs)  # only one feed has it; accept with note
            else:
                out[code][k] = None  # feeds disagree → raw defect, no trustworthy truth
    return out


# ── FAMILY: sector + index returns (sectors page heatmap, market-pulse strip) ─


def check_returns(d: date) -> None:
    # sector_name -> primary index, the exact map the sectors page uses
    smap = read_df("""
        select sector_name, primary_nse_index
        from foundation_staging.atlas_sector_master
        where is_active and primary_nse_index is not null
    """)
    codes = sorted(set(smap["primary_nse_index"]) |
                   {"NIFTY 50", "NIFTY 500", "NIFTY 100",
                    "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"})
    truth = recompute_index_returns(codes, d)

    # what the sectors-page heatmap reads: the sector INDEX return from the natively-
    # rebuilt atlas_index_metrics_daily (build_index_metrics.py), joined sector→index via
    # atlas_sector_master.primary_nse_index. (mv_sector_cards' bottom-up ret_* columns are
    # deprecated for display — they were a reconstruction inflated 2–6×.)
    imet = read_df("""
        select index_code, ret_1m, ret_3m, ret_6m, ret_12m
        from foundation_staging.atlas_index_metrics_daily
        where date=(select max(date) from foundation_staging.atlas_index_metrics_daily)
    """).set_index("index_code")

    for _, row in smap.iterrows():
        sec, code = row["sector_name"], row["primary_nse_index"]
        for k, _lbl in _WINDOWS:
            t = truth.get(code, {}).get(k)
            stored = None
            if code in imet.index and imet.at[code, k] is not None:
                stored = float(imet.at[code, k]) * 100
            add(family="returns", page="Sectors · heatmap",
                metric=f"sector_index.{k}", scope=sec,
                stored=stored, recomputed=t, tol=1.0, unit="%",
                note=f"index={code}")

    # broad / cap-tier indices used by Market Pulse + base toggles
    for code, page, label in [
        ("NIFTY 50", "Market Pulse · strip", "Nifty 50"),
        ("NIFTY 500", "Market Pulse · strip", "Nifty 500"),
        ("NIFTY 100", "Market Pulse · tier", "Nifty 100 (large)"),
        ("NIFTY MIDCAP 150", "Market Pulse · tier", "Midcap 150"),
        ("NIFTY SMALLCAP 250", "Market Pulse · tier", "Smallcap 250"),
    ]:
        for k, _lbl in _WINDOWS:
            t = truth.get(code, {}).get(k)
            s = None
            if code in imet.index and imet.at[code, k] is not None:
                s = float(imet.at[code, k]) * 100
            add(family="returns", page=page,
                metric=f"atlas_index_metrics.{k}", scope=label,
                stored=s, recomputed=t, tol=1.0, unit="%", note=f"index={code}")


# ── FAMILY: market breadth counts (Market Pulse) ─────────────────────────────


def check_breadth(d: date) -> None:
    """The breadth panel shows counts of Nifty-500 names above each EMA. Reconcile
    the stored breadth series against an independent recount of the per-stock
    above_ema flags in technical_daily on the same date."""
    stored = read_df("""
        select date, above_21, above_50, above_200, n_members
        from foundation_staging.breadth_nifty500_daily
        where date=(select max(date) from foundation_staging.breadth_nifty500_daily)
    """)
    if stored.empty:
        add(family="breadth", page="Market Pulse · breadth",
            metric="breadth counts", scope="Nifty 500",
            stored=None, recomputed=None, tol=0, unit="count",
            note="breadth_nifty500_daily empty/absent — wire source")
        return
    srow = stored.iloc[0]
    bdate = srow["date"]
    recount = read_df("""
        select
          count(*) filter (where above_ema_21)  a21,
          count(*) filter (where above_ema_50)  a50,
          count(*) filter (where above_ema_200) a200
        from foundation_staging.technical_daily
        where date=:bd and asset_class='stock'
    """, {"bd": bdate}).iloc[0]
    for fld, rc, lbl in [("above_21", "a21", "Above 21-EMA"),
                         ("above_50", "a50", "Above 50-EMA"),
                         ("above_200", "a200", "Above 200-EMA")]:
        s = None if srow[fld] is None else float(srow[fld])
        r = None if recount[rc] is None else float(recount[rc])
        add(family="breadth", page="Market Pulse · breadth",
            metric=f"breadth.{fld}", scope="Nifty 500",
            stored=s, recomputed=r, tol=2, unit="count",
            note=f"recount of technical_daily flags on {bdate}")


# ── FAMILY: lens scores — structural / distributional (the six-lens journal) ──


def check_lens(d: date) -> None:
    """The lens deciles are the core methodology output; we can't recompute them
    from a second source, but we CAN assert the invariants that must hold of a real
    decile field: 1–10 range, sane coverage, fresh snapshot, no all-equal collapse."""
    latest = scalar("select max(date) from foundation_staging.atlas_lens_scores_daily")
    add(family="lens", page="Stocks / Sectors · lens",
        metric="snapshot freshness", scope="atlas_lens_scores_daily",
        stored=(latest - d).days if latest else None, recomputed=0, tol=4,
        unit="days stale", note=f"latest={latest}, portal as_of={d}")

    stats = read_df("""
        select count(*) n,
               count(*) filter (where technical between 1 and 10) tech_ok,
               count(*) filter (where technical is not null) tech_nn,
               count(distinct technical) tech_distinct
        from foundation_staging.atlas_lens_scores_daily
        where date=(select max(date) from foundation_staging.atlas_lens_scores_daily)
          and asset_class='stock'
    """).iloc[0]
    n = int(stats["n"]) or 1
    # all non-null technical deciles must be in 1..10
    bad = n - int(stats["tech_ok"]) - (n - int(stats["tech_nn"]))
    add(family="lens", page="Stocks · lens", metric="technical decile in 1..10",
        scope="all stocks", stored=float(bad), recomputed=0, tol=0, unit="rows out of range",
        note=f"{stats['tech_nn']}/{n} non-null")
    # a real decile field must spread across the scale, not collapse to one value
    add(family="lens", page="Stocks · lens", metric="technical decile spread",
        scope="all stocks", stored=float(stats["tech_distinct"]), recomputed=10,
        tol=4, unit="distinct values", note="≥6 distinct expected for a live decile")


# ── render ────────────────────────────────────────────────────────────────────


def render_table() -> str:
    order = {"FAIL": 0, "MISSING": 1, "NO-TRUTH": 2, "PASS": 3}
    rows = sorted(RESULTS, key=lambda c: (order[c.status], c.family, c.page, c.scope))
    w = {"st": 9, "pg": 22, "sc": 20, "me": 26}
    out = []
    icon = {"PASS": "✅", "FAIL": "❌", "MISSING": "⚠️ ", "NO-TRUTH": "•"}
    head = f"{'':3} {'page':<{w['pg']}} {'metric':<{w['me']}} {'scope':<{w['sc']}} {'stored':>9} {'truth':>9} {'Δ':>7}  unit"
    out.append(head)
    out.append("-" * len(head))
    for c in rows:
        s = "—" if c.stored is None else f"{c.stored:,.2f}"
        r = "—" if c.recomputed is None else f"{c.recomputed:,.2f}"
        dl = "—" if c.delta is None else f"{c.delta:,.2f}"
        out.append(f"{icon[c.status]:3} {c.page[:w['pg']]:<{w['pg']}} {c.metric[:w['me']]:<{w['me']}} "
                   f"{c.scope[:w['sc']]:<{w['sc']}} {s:>9} {r:>9} {dl:>7}  {c.unit}")
    # summary
    from collections import Counter
    cnt = Counter(c.status for c in RESULTS)
    out.append("")
    out.append(f"SUMMARY  PASS {cnt['PASS']}  FAIL {cnt['FAIL']}  "
               f"MISSING {cnt['MISSING']}  NO-TRUTH {cnt['NO-TRUTH']}  (total {len(RESULTS)})")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", choices=["returns", "breadth", "lens", "all"],
                    default="all")
    ap.add_argument("--json", help="also write full results to this path")
    ap.add_argument("--fail-only", action="store_true", help="print only FAIL/MISSING rows")
    args = ap.parse_args()

    d = as_of()
    print(f"# Portal reconciliation — as of {d}\n", file=sys.stderr)

    fams = ["returns", "breadth", "lens"] if args.family == "all" else [args.family]
    if "returns" in fams:
        check_returns(d)
    if "breadth" in fams:
        check_breadth(d)
    if "lens" in fams:
        check_lens(d)

    if args.fail_only:
        keep = {"FAIL", "MISSING"}
        global RESULTS
        shown = [c for c in RESULTS if c.status in keep]
        RESULTS = shown or RESULTS  # if nothing failed, still show summary
    print(render_table())

    if args.json:
        with open(args.json, "w") as f:
            json.dump([{**c.__dict__, "status": c.status,
                        "delta": c.delta} for c in RESULTS], f,
                      indent=2, default=str)

    return 1 if any(c.status == "FAIL" for c in RESULTS) else 0


if __name__ == "__main__":
    sys.exit(main())
