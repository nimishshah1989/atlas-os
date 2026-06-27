#!/usr/bin/env python3
"""Set-based, in-DB recompute of the journal composite from the persisted DB weights.

The composite is a weighted average of the (rescaled) conviction-lens columns that
already live in atlas_lens_scores_daily — so it is computed entirely inside Postgres
with one UPDATE (no 3.9M-row read/write over the wire, no per-row Python). Faithful
to atlas.lenses.compute.composite.compute_composite (rescale → coverage-weighted
avg → convergence bonus → valuation multiplier + modifiers → conviction tier);
policy excluded (FYI-only), valuation is the multiplier.

    python recompute_sql.py --verify     # compare SQL vs canonical scorer on a sample (no write)
    python recompute_sql.py --apply      # verify, then run the single in-DB UPDATE
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import itertools  # noqa: E402

import _db  # noqa: E402

from atlas.db import load_thresholds  # noqa: E402
from atlas.lenses.compute.composite import BREAKPOINTS  # noqa: E402

CONV = ["technical", "fundamental", "catalyst", "flow"]  # policy excluded (FYI)


def _rescale_sql(col: str) -> str:
    """Piecewise-linear rescale of *col* through its breakpoints, as a SQL CASE
    (NULL when the lens is absent, i.e. raw <= 0). Mirrors composite._rescale,
    rounded to 2 dp to match the scorer's quantize."""
    bps = BREAKPOINTS[col]
    parts = [f"WHEN {col} IS NULL OR {col} <= {bps[0][0]} THEN NULL"]
    for (x0, y0), (x1, y1) in itertools.pairwise(bps):
        # within (x0, x1]: y0 + (raw-x0)/(x1-x0)*(y1-y0)
        parts.append(
            f"WHEN {col} <= {x1} THEN round(({y0} + ({col}-{x0})::numeric/{x1 - x0}*{y1 - y0})::numeric, 2)"
        )
    parts.append(f"ELSE {bps[-1][1]}")
    return "CASE " + " ".join(parts) + " END"


def build_sql(weights: dict, th: dict, where_extra: str = "", schema: str = "atlas") -> str:
    w = {l: float(weights[l]) for l in CONV}
    conv_thr = float(th.get("lens_convergence_threshold", 40))
    c2 = float(th.get("lens_convergence_2", 1.06))
    c3 = float(th.get("lens_convergence_3", 1.10))
    c4 = float(th.get("lens_convergence_4plus", 1.15))
    hi_s = float(th.get("lens_conviction_highest_score", 70))
    hi_l = int(float(th.get("lens_conviction_highest_min_layers", 3)))
    h_s = float(th.get("lens_conviction_high_score", 58))
    h_l = int(float(th.get("lens_conviction_high_min_layers", 2)))
    m_s = float(th.get("lens_conviction_medium_score", 45))
    wa_s = float(th.get("lens_conviction_watch_score", 30))

    resc = ",\n".join(f"    {_rescale_sql(l)} AS r_{l}" for l in CONV)
    # present-weight + weighted sum + convergence count + active count
    tw = " + ".join(f"(CASE WHEN r_{l} IS NOT NULL THEN {w[l]} ELSE 0 END)" for l in CONV)
    wsum = " + ".join(f"(CASE WHEN r_{l} IS NOT NULL THEN r_{l}*{w[l]} ELSE 0 END)" for l in CONV)
    conv = " + ".join(f"(CASE WHEN r_{l} >= {conv_thr} THEN 1 ELSE 0 END)" for l in CONV)
    active = " + ".join(f"(CASE WHEN r_{l} IS NOT NULL THEN 1 ELSE 0 END)" for l in CONV)

    return f"""
WITH base AS (
  SELECT instrument_id, date, valuation_multiplier, smart_money_score, degradation_score,
{resc}
  FROM atlas.atlas_lens_scores_daily
  WHERE asset_class='stock'{where_extra}
), agg AS (
  SELECT *,
    ({tw})::numeric AS tw,
    ({wsum})::numeric AS wsum,
    ({conv})::int AS converging,
    ({active})::int AS lenses_active
  FROM base
), calc AS (
  SELECT *,
    CASE WHEN tw > 0 THEN (wsum/tw) * sqrt(tw) ELSE 0 END AS weighted_avg,
    sqrt(tw) AS coverage_factor,
    CASE WHEN converging >= 4 THEN {c4} WHEN converging >= 3 THEN {c3}
         WHEN converging >= 2 THEN {c2} ELSE 1.0 END AS conv_mult,
    LEAST(1.15, GREATEST(0.75, COALESCE(valuation_multiplier, 1.0))) AS val_mult
  FROM agg
), fin AS (
  SELECT instrument_id, date, lenses_active,
    round(coverage_factor::numeric, 2) AS coverage_factor,
    round(LEAST(100, GREATEST(0,
      LEAST(100, GREATEST(0, weighted_avg*conv_mult)) * val_mult
      + COALESCE(smart_money_score,0) + COALESCE(degradation_score,0)))::numeric, 2) AS composite
  FROM calc
)
SELECT instrument_id, date, composite, coverage_factor, lenses_active,
  CASE WHEN composite >= {hi_s} AND lenses_active >= {hi_l} THEN 'HIGHEST'
       WHEN composite >= {h_s} AND lenses_active >= {h_l} THEN 'HIGH'
       WHEN composite >= {m_s} THEN 'MEDIUM'
       WHEN composite >= {wa_s} THEN 'WATCH'
       ELSE 'BELOW_THRESHOLD' END AS conviction_tier
FROM fin
"""


def verify(weights, th) -> bool:
    """Compare the SQL composite to the canonical compute_composite on a real sample."""
    import pandas as pd

    from atlas.lenses.compute.composite import compute_composite
    from atlas.lenses.compute.thresholds_view import nest_thresholds

    mx = _db.scalar("SELECT max(date) FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock'")
    sql_sel = build_sql(weights, th, where_extra=" AND date = :d")
    got = _db.read_df(sql_sel.replace(":d", f"'{mx}'")).set_index("instrument_id")
    raw = _db.read_df(
        "SELECT instrument_id, technical, fundamental, valuation, catalyst, flow, policy, "
        "valuation_multiplier, smart_money_score, degradation_score "
        "FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock' AND date=:d",
        {"d": mx},
    ).set_index("instrument_id")
    thn = nest_thresholds({k: (float(v) if isinstance(v, Decimal) else v) for k, v in th.items()})

    def f(v):
        return float(v) if v is not None and pd.notna(v) else None

    bad = 0
    for iid in raw.index[:500]:
        r = raw.loc[iid]
        c = compute_composite(
            technical=f(r.technical),
            fundamental=f(r.fundamental),
            valuation_score=f(r.valuation),
            catalyst=f(r.catalyst),
            flow=f(r.flow),
            policy=f(r.policy),
            valuation_multiplier=f(r.valuation_multiplier) or 1.0,
            smart_money_score=f(r.smart_money_score) or 0.0,
            degradation_score=f(r.degradation_score) or 0.0,
            thresholds=thn,
        )
        sql_c = float(got.loc[iid, "composite"]) if iid in got.index else None
        if sql_c is None or abs(sql_c - float(c.final_score)) > 0.1:
            bad += 1
            if bad <= 5:
                print(
                    f"   mismatch {iid}: sql={sql_c} canonical={c.final_score} "
                    f"tier sql={got.loc[iid, 'conviction_tier']} canon={c.conviction_tier}"
                )
    print(f"   verify: {500 - bad}/500 match within 0.1 (composite)")
    return bad == 0


def _pg_connect():
    """Raw psycopg2 connection with TCP KEEPALIVES so a dropped Supabase connection
    raises promptly instead of hanging forever (the failure mode that stalled the
    first attempt). Bounded statement timeout so a stuck statement cancels, not hangs."""
    import psycopg2

    dsn = _db.db_url().replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(
        dsn,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        options="-c statement_timeout=300000",
    )  # 300s/statement
    conn.autocommit = False
    return conn


def apply_robust(weights, th, start_year: int):
    """Materialize composites month-by-month (small batches) with keepalives + retry.
    Resumable: only touches >= start_year."""
    import time

    import psycopg2

    mn, mx = (
        _db.scalar("SELECT min(date) FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock'"),
        _db.scalar("SELECT max(date) FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock'"),
    )
    # month windows from max(start_year-01, mn) .. mx
    months = []
    y, m = max(start_year, mn.year), 1 if start_year > mn.year else mn.month
    while (y, m) <= (mx.year, mx.month):
        months.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1
    print(f"   {len(months)} monthly batches from {months[0]} to {months[-1]}", flush=True)
    t0 = time.time()
    for y, m in months:
        lo = f"{y}-{m:02d}-01"
        hi = f"{y}-{m:02d}-31"
        sel = build_sql(weights, th, where_extra=f" AND date >= '{lo}' AND date <= '{hi}'")
        upd = (
            f"WITH src AS ({sel}) UPDATE atlas.atlas_lens_scores_daily l "
            "SET composite=src.composite, conviction_tier=src.conviction_tier, "
            "coverage_factor=src.coverage_factor, lenses_active=src.lenses_active "
            "FROM src WHERE l.instrument_id=src.instrument_id AND l.date=src.date AND l.asset_class='stock'"
        )
        for attempt in range(1, 4):
            conn = None
            try:
                conn = _pg_connect()
                with conn.cursor() as cur:
                    cur.execute(upd)
                    nrows = cur.rowcount
                conn.commit()
                print(f"   {y}-{m:02d}: {nrows} rows ({time.time() - t0:.0f}s)", flush=True)
                break
            except (psycopg2.OperationalError, psycopg2.errors.QueryCanceled) as e:
                print(
                    f"   {y}-{m:02d} attempt {attempt} failed: {repr(e)[:80]}; retrying", flush=True
                )
                time.sleep(3)
            finally:
                if conn is not None:
                    conn.close()
        else:
            print(f"   ❌ {y}-{m:02d} failed after 3 attempts", flush=True)
            sys.exit(1)
    print(f"✅ robust recompute done in {time.time() - t0:.0f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--robust", action="store_true", help="month-batched, keepalive, retry")
    ap.add_argument("--start-year", type=int, default=2019)
    args = ap.parse_args()
    raw = load_thresholds()
    th = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in raw.items()}
    weights = {l: float(th[f"lens_weight_{l}"]) for l in CONV}
    print(f"weights: {weights}")

    ok = verify(weights, th)
    if not ok:
        print("❌ SQL composite diverges from canonical scorer — NOT applying.")
        sys.exit(1)
    print("✅ SQL matches canonical scorer.")
    if args.robust:
        apply_robust(weights, th, args.start_year)
        return
    if not args.apply:
        print("verify-only; re-run with --apply to UPDATE.")
        return

    # One-time materialization. The math is in-DB (no rows on the wire); the only
    # cost is Postgres physically rewriting 3.9M indexed rows, so we batch by year
    # (short transactions) with the per-session statement timeout lifted.
    import time

    from atlas.db import get_engine

    raw = get_engine().raw_connection()
    t0 = time.time()
    try:
        with raw.cursor() as cur:
            cur.execute("SET statement_timeout = 0")  # lift the 600s cap for this session
            cur.execute(
                "SELECT min(date), max(date) FROM atlas.atlas_lens_scores_daily "
                "WHERE asset_class='stock'"
            )  # indexed, fast
            mn, mx = cur.fetchone()
            years = list(range(mn.year, mx.year + 1))
            print(f"   recomputing {mn}..{mx} by year: {years}", flush=True)
            for yr in years:
                sel = build_sql(
                    weights, th, where_extra=f" AND date >= '{yr}-01-01' AND date <= '{yr}-12-31'"
                )
                cur.execute(
                    f"WITH src AS ({sel}) "
                    "UPDATE atlas.atlas_lens_scores_daily l "
                    "SET composite=src.composite, conviction_tier=src.conviction_tier, "
                    "coverage_factor=src.coverage_factor, lenses_active=src.lenses_active "
                    "FROM src WHERE l.instrument_id=src.instrument_id AND l.date=src.date "
                    "AND l.asset_class='stock'"
                )
                raw.commit()
                print(
                    f"   {yr}: {cur.rowcount} rows  ({time.time() - t0:.0f}s elapsed)", flush=True
                )
    finally:
        raw.close()
    print(f"✅ in-DB recompute done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
