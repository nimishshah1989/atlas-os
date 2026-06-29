#!/usr/bin/env python3
"""Daily FUND-RANK HISTORY — foundation_staging.fund_rank_daily.

A fund's rank moves every day even though its holdings are only refreshed monthly,
because the rank is the holdings-weighted lens composite re-scored against THAT day's
stock lens scores. So we can build a daily rank series from ~Feb-2026 (first usable
holdings snapshot) to today by, for each trading day D:

  1. CARRY-FORWARD holdings: the latest monthly snapshot with as_of_date <= D.
  2. Score each holding with that day's stock lens scores (atlas_lens_scores_daily @ D),
     deciles computed within the cap cohort exactly as the live SCORED_STOCKS CTE does.
  3. Roll up to a holdings-weighted lens vector (v_tech/v_fund/v_cat/v_flow + breadth) —
     the SAME FILTER expressions as frontend/src/lib/queries/v6/fund_lens.ts (ROLLUP).
  4. Blend to a composite and rank WITHIN the SEBI category over funds with >= 5 scored
     holdings — via fund_rank_core (the faithful port of fundScore.ts), so the D = today
     row equals exactly what the funds page renders.

Weights come from foundation_staging.atlas_thresholds (the /thresholds panel) — never
hard-coded. Idempotent: re-running a date range DELETEs then re-INSERTs those days.

    python build_fund_rank_history.py                 # full backfill (first snapshot -> latest lens date)
    python build_fund_rank_history.py --latest        # just the newest lens date (nightly append)
    python build_fund_rank_history.py --start 2026-06-01 --end 2026-06-29
    python build_fund_rank_history.py --rebuild        # drop + full rebuild
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/foundation -> _db, fund_rank_core

import fund_rank_core as core
import pandas as pd
import _db

TGT = "foundation_staging.fund_rank_daily"

# Identical to fund_lens.ts EQUITY_FUND_FILTER — one scheme per portfolio (no Direct/IDCW dupes),
# equity only. Keeps the ranked cohort identical to what the funds page displays.
EQUITY_FUND_FILTER = """NOT mm.is_etf AND mm.is_active
  AND mm.broad_category NOT ILIKE ALL(ARRAY['%debt%','%liquid%','%money%','%overnight%','%gilt%','%bond%'])
  AND mm.fund_name NOT ILIKE '%Direct%' AND mm.fund_name NOT ILIKE '%Dir Gr%' AND mm.fund_name NOT ILIKE '%IDCW%'"""

DDL = f"""
CREATE TABLE IF NOT EXISTS {TGT} (
  date        date        NOT NULL,
  mstar_id    varchar(32) NOT NULL,
  category    varchar(128),
  composite   numeric(7,3),
  breadth     numeric(7,4),
  n_scored    integer,
  cat_rank    integer,
  cat_size    integer,
  pct_band    text,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (mstar_id, date)
);
CREATE INDEX IF NOT EXISTS ix_fund_rank_daily_date ON {TGT} (date);
CREATE INDEX IF NOT EXISTS ix_fund_rank_daily_cat_date ON {TGT} (category, date);
"""

# Per-day rollup: holdings-weighted lens vector per fund @ date :d, carry-forward holdings.
# Mirrors fund_lens.ts ROLLUP + SCORED_STOCKS (deciles within cap cohort) EXACTLY.
ROLLUP_SQL = """
WITH cap AS (
  SELECT instrument_id,
    CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
         WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
         WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
  FROM foundation_staging.de_index_constituents
  WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
  GROUP BY instrument_id),
j AS (
  -- INNER JOIN instrument_master mirrors the production SCORED_STOCKS CTE exactly, so the
  -- ntile decile cohort (and therefore lead -> breadth, the rank tiebreaker) is identical.
  SELECT l.instrument_id, COALESCE(c.cap,'micro') AS cap,
         l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl
  FROM foundation_staging.atlas_lens_scores_daily l
  JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
  LEFT JOIN cap c ON c.instrument_id = l.instrument_id
  WHERE l.asset_class='stock' AND l.date = :d),
dec AS (
  SELECT instrument_id, t, f, ca, fl,
    CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
    CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow
  FROM j),
scored AS (
  SELECT instrument_id, t, f, ca, fl,
    (COALESCE((d_tech>=9)::int,0)+COALESCE((d_flow>=9)::int,0)) AS lead
  FROM dec),
snap AS (SELECT max(as_of_date) AS d FROM foundation_staging.de_mf_holdings WHERE as_of_date <= :d)
SELECT mm.mstar_id, mm.category_name AS category,
  count(h.instrument_id) AS n_scored,
  sum(h.weight_pct) FILTER (WHERE COALESCE(s.lead,0) >= 2) / NULLIF(sum(h.weight_pct),0) AS breadth,
  sum(h.weight_pct*s.t)  FILTER (WHERE s.t  IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.t  IS NOT NULL),0) AS v_tech,
  sum(h.weight_pct*s.f)  FILTER (WHERE s.f  IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.f  IS NOT NULL),0) AS v_fund,
  sum(h.weight_pct*s.ca) FILTER (WHERE s.ca IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.ca IS NOT NULL),0) AS v_cat,
  sum(h.weight_pct*s.fl) FILTER (WHERE s.fl IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.fl IS NOT NULL),0) AS v_flow
FROM foundation_staging.de_mf_master mm
JOIN foundation_staging.de_mf_holdings h
  ON h.mstar_id = mm.mstar_id AND h.as_of_date = (SELECT d FROM snap) AND h.weight_pct > 0
JOIN scored s ON s.instrument_id = h.instrument_id
WHERE """ + EQUITY_FUND_FILTER + """
GROUP BY mm.mstar_id, mm.category_name
HAVING count(h.instrument_id) >= 5
"""


def _weights() -> dict:
    """The live composite weights from foundation_staging.atlas_thresholds (same row the
    frontend's getLensWeights reads), so backend history and frontend page agree."""
    df = _db.read_df(
        """SELECT threshold_key, threshold_value FROM foundation_staging.atlas_thresholds
           WHERE threshold_key IN ('lens_weight_technical','lens_weight_fundamental',
                                   'lens_weight_flow','lens_weight_catalyst')"""
    )
    m = {r.threshold_key: float(r.threshold_value) for r in df.itertuples()}
    return {
        "technical": m.get("lens_weight_technical", 0.30),
        "fundamental": m.get("lens_weight_fundamental", 0.25),
        "flow": m.get("lens_weight_flow", 0.25),
        "catalyst": m.get("lens_weight_catalyst", 0.20),
    }


def _trading_days(start: str | None, end: str | None) -> list:
    """Distinct stock-lens dates in range — the days a fund rank can be computed for."""
    df = _db.read_df(
        """SELECT DISTINCT date FROM foundation_staging.atlas_lens_scores_daily
           WHERE asset_class='stock'
             AND (CAST(:s AS date) IS NULL OR date >= CAST(:s AS date))
             AND (CAST(:e AS date) IS NULL OR date <= CAST(:e AS date)) ORDER BY date""",
        {"s": start, "e": end},
    )
    return [d.date() if hasattr(d, "date") else d for d in df["date"].tolist()]


def _default_start() -> str:
    """First holdings snapshot with a real cohort (>= 20 funds) — earlier 1-fund stubs
    (e.g. the lone 2026-01-31 row) can't produce category ranks."""
    return str(
        _db.scalar(
            """SELECT min(as_of_date) FROM (
                 SELECT as_of_date FROM foundation_staging.de_mf_holdings
                 GROUP BY as_of_date HAVING count(DISTINCT mstar_id) >= 20) q"""
        )
    )


def build_day(day, weights: dict) -> pd.DataFrame:
    """One day's ranked rows (composite + cat_rank + cat_size + pct_band) via fund_rank_core."""
    df = _db.read_df(ROLLUP_SQL, {"d": str(day)})
    if df.empty:
        return df
    rows = []
    for r in df.itertuples():
        vec = {"v_tech": r.v_tech, "v_fund": r.v_fund, "v_flow": r.v_flow, "v_cat": r.v_cat}
        rows.append({
            "mstar_id": r.mstar_id, "category": r.category,
            "breadth": float(r.breadth) if r.breadth is not None else None,
            "n_scored": int(r.n_scored),
            "composite": core.composite(vec, weights),
        })
    ranked = [r for r in core.rank_in_category(rows) if r["composite"] is not None]
    out = pd.DataFrame(ranked)
    if out.empty:
        return out
    out["date"] = day
    out["composite"] = out["composite"].round(3)
    return out[["date", "mstar_id", "category", "composite", "breadth", "n_scored",
                "cat_rank", "cat_size", "pct_band"]]


def run(start: str | None, end: str | None, rebuild: bool, latest: bool) -> None:
    if rebuild:
        _db.exec_sql(f"DROP TABLE IF EXISTS {TGT} CASCADE")
    _db.exec_script(DDL)

    if latest:
        mx = _db.scalar(
            "SELECT max(date) FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'"
        )
        start = end = str(mx)
    else:
        start = start or _default_start()
        end = end or str(
            _db.scalar(
                "SELECT max(date) FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'"
            )
        )

    days = _trading_days(start, end)
    if not days:
        print(f"no stock-lens dates in {start}..{end}; nothing to do")
        return
    weights = _weights()
    print(f"building {TGT}: {len(days)} days {days[0]}..{days[-1]} · weights={weights}")

    # idempotent: clear the range, then insert day by day
    _db.exec_sql(f"DELETE FROM {TGT} WHERE date BETWEEN :a AND :b", {"a": str(days[0]), "b": str(days[-1])})
    total = 0
    for i, day in enumerate(days):
        out = build_day(day, weights)
        if out.empty:
            continue
        total += _db.upsert_df(TGT, out, conflict_cols=["mstar_id", "date"])
        if i % 10 == 0 or i == len(days) - 1:
            print(f"  [{i+1}/{len(days)}] {day}: {len(out)} funds (running total {total})")
    print(f"done: {total} fund-day rows across {len(days)} days")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", help="first date (YYYY-MM-DD); default = first usable holdings snapshot")
    ap.add_argument("--end", help="last date (YYYY-MM-DD); default = latest stock-lens date")
    ap.add_argument("--latest", action="store_true", help="only the newest lens date (nightly append)")
    ap.add_argument("--rebuild", action="store_true", help="DROP + full rebuild")
    args = ap.parse_args()
    run(args.start, args.end, args.rebuild, args.latest)


if __name__ == "__main__":
    main()
