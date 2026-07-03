#!/usr/bin/env python3
"""Lean sector-card builder — rebuilds the three derived sector board tables
(mv_sector_cards / mv_sector_breadth / mv_sector_deepdive) DIRECTLY from the
fresh single-schema sources, replacing the 1351-line atlas/compute/sectors.py
chain (+ its deleted atlas.compute._session deps) removed in the consolidation
purge (73fc760e). Those three tables silently froze at 06-24/25 while the board
still read them; this restores a producer that only touches fresh tables.

Sources (all fresh to EOD):
  * atlas_index_metrics_daily × atlas_sector_master.primary_nse_index
      → per-sector TOP-DOWN returns + RS vs Nifty 500. The old cards' bottom-up
        reconstruction was inflated 2-5×; the board already routes returns
        through these index metrics (getSectorIndexRs), so cards now match.
  * technical_daily × instrument_master.sector
      → bottom-up breadth (%>EMA21/50/200, %at-52wH), movers, strength quintiles.
  * atlas_lens_scores_daily × de_index_constituents (cap cohort)
      → leaders = TOP DECILE (D10) of composite within cap cohort (the one
        canonical leader rule, reused from etf_lens.SCORED_STOCKS) + conviction
        distribution.

Scale conventions match what each consumer already expects (verified against the
live components): cards ret_*/rs_*/pct_* are FRACTIONS (0.0076 = 0.76%);
deepdive returns/rs_windows are PERCENT/PP (human units); deepdive pct_* are
fractions. Nothing is fabricated — a sector with no index metrics is skipped, a
missing value is NULL. RULE #0.

Run:
  python scripts/foundation/build_sector_cards.py
Wire after rollup_sectors in scripts/ops/atlas_daily.sh.
"""

from __future__ import annotations

import datetime as dt
import json

import _db
import numpy as np
import pandas as pd

M = "atlas_foundation"
N500 = "NIFTY 500"
STRONG_TIER = ["HIGHEST", "HIGH"]
MED_TIER = ["MEDIUM"]
WINDOWS = [("1W", "ret_1w"), ("1M", "ret_1m"), ("3M", "ret_3m"), ("6M", "ret_6m")]


def _ensure_unique_index(table: str, cols: list[str], name: str) -> None:
    """Unique index on `cols` so upsert_df's ON CONFLICT has a target. The tables
    shipped with only a non-unique sector_name index; dedup any pre-existing rows
    (keep the newest ctid) then add the unique key. Idempotent."""
    if _db.scalar(
        "select 1 from pg_indexes where schemaname=:s and tablename=:t and indexname=:n",
        {"s": M, "t": table, "n": name},
    ):
        return
    on = " and ".join(f"a.{c} = b.{c}" for c in cols)
    _db.exec_sql(f"delete from {M}.{table} a using {M}.{table} b where a.ctid < b.ctid and {on}")
    _db.exec_sql(f"create unique index {name} on {M}.{table} ({', '.join(cols)})")


def _sector_index_returns() -> tuple[pd.DataFrame, dict]:
    """Per-sector top-down index returns (fractions) + the Nifty 500 base row."""
    df = _db.read_df(f"""
        SELECT sm.sector_name,
               im.ret_1w, im.ret_1m, im.ret_3m, im.ret_6m, im.ret_12m
        FROM {M}.atlas_index_metrics_daily im
        JOIN {M}.atlas_sector_master sm
          ON sm.primary_nse_index = im.index_code
         AND sm.is_active = true
         AND lower(sm.sector_name) NOT LIKE '%conglomerate%'
        WHERE im.date = (SELECT max(date) FROM {M}.atlas_index_metrics_daily)
        ORDER BY sm.sector_name
    """)
    base = _db.read_df(
        f"""
        SELECT ret_1w, ret_1m, ret_3m, ret_6m, ret_12m
        FROM {M}.atlas_index_metrics_daily
        WHERE index_code = :b
          AND date = (SELECT max(date) FROM {M}.atlas_index_metrics_daily)
    """,
        {"b": N500},
    )
    n500 = {
        c: float(base.iloc[0][c]) if base.iloc[0][c] is not None else None for c in base.columns
    }
    return df, n500


def _stock_frame() -> pd.DataFrame:
    """Per-stock: sector, symbol, breadth flags, window returns, composite decile
    within cap cohort, conviction tier — all at the latest lens/technical date."""
    return _db.read_df(f"""
        WITH tdl AS (SELECT max(date) d FROM {M}.technical_daily WHERE asset_class='stock'),
             ll  AS (SELECT max(date) d FROM {M}.atlas_lens_scores_daily WHERE asset_class='stock'),
             cap AS (
               SELECT instrument_id,
                 CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
                      WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
                      WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
               FROM {M}.de_index_constituents
               WHERE effective_to IS NULL
                 AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
               GROUP BY instrument_id),
             dec AS (
               SELECT l.instrument_id, l.conviction_tier,
                 ntile(10) OVER (PARTITION BY COALESCE(c.cap,'micro') ORDER BY l.composite) AS d_comp
               FROM {M}.atlas_lens_scores_daily l
               LEFT JOIN cap c ON c.instrument_id = l.instrument_id
               WHERE l.asset_class='stock' AND l.date=(SELECT d FROM ll) AND l.composite IS NOT NULL)
        SELECT im.sector, td.symbol,
               td.above_ema_21, td.above_ema_50, td.above_ema_200, td.pos_52w,
               td.ret_1w::float ret_1w, td.ret_1m::float ret_1m,
               td.ret_3m::float ret_3m, td.ret_6m::float ret_6m,
               dec.d_comp, dec.conviction_tier
        FROM {M}.technical_daily td
        JOIN {M}.instrument_master im ON im.instrument_id = td.instrument_id
        LEFT JOIN dec ON dec.instrument_id = td.instrument_id
        WHERE td.asset_class='stock' AND td.date=(SELECT d FROM tdl)
          AND im.sector IS NOT NULL AND im.sector <> ''
    """)


def _num(x: object) -> float | None:
    """None/NaN → None, else float. NaN must become SQL NULL (json.dumps('NaN') is invalid)."""
    return None if pd.isna(x) else float(x)  # type: ignore[arg-type]


def _quintile_counts(rets: pd.Series) -> dict:
    """NTILE(5) on 3M return → strength buckets (very_strong = top 20%)."""
    r = rets.dropna()
    keys = ["very_weak", "weak", "neutral", "strong", "very_strong"]
    out = {k: 0 for k in keys}
    if r.empty:
        return out
    # rank-based ntile(5): even split by order, ties broken by position (matches SQL ntile)
    q = (r.rank(method="first") - 1) * 5 // len(r)
    for bucket in q:
        out[keys[int(bucket)]] += 1
    return out


def _movers(g: pd.DataFrame, col: str, top: bool, n: int = 5) -> list[dict]:
    d = g.dropna(subset=[col]).sort_values(col, ascending=not top).head(n)
    return [
        {"symbol": s, "ret_pct": round(float(v) * 100, 2)}
        for s, v in zip(d["symbol"], d[col], strict=False)
    ]


def _verdicts(idx: pd.DataFrame, n500: dict) -> dict:
    """Verdict per sector = tercile rank of 3M RS vs Nifty 500 (glass-box, no
    tuned threshold): top third Overweight, bottom third Underweight, else Neutral."""
    base3 = n500.get("ret_3m")
    rs3 = idx.apply(
        lambda r: (
            (float(r["ret_3m"]) - base3)
            if (r["ret_3m"] is not None and base3 is not None)
            else np.nan
        ),
        axis=1,
    )
    order = rs3.rank(method="first")
    n = order.notna().sum()
    out = {}
    for sec, rk in zip(idx["sector_name"], order, strict=False):
        if pd.isna(rk):
            out[sec] = ("Neutral", "NW")
        elif rk > n * 2 / 3:
            out[sec] = ("Overweight", "OW")
        elif rk <= n / 3:
            out[sec] = ("Underweight", "UW")
        else:
            out[sec] = ("Neutral", "NW")
    return out


def build() -> None:
    idx, n500 = _sector_index_returns()
    if idx.empty:
        raise RuntimeError(
            "no sector index metrics — atlas_index_metrics_daily empty for latest date"
        )
    stk = _stock_frame()
    if stk.empty:
        raise RuntimeError("no stock rows — technical_daily/instrument_master join empty")

    as_of = _db.scalar(f"select max(date) from {M}.atlas_index_metrics_daily")
    tech_asof = _db.scalar(f"select max(date) from {M}.technical_daily where asset_class='stock'")
    now = dt.datetime.now(dt.UTC)
    verdicts = _verdicts(idx, n500)

    # universe-wide top-decile threshold per window (for breadth_by_window.pct_top_decile_movers)
    dec_thresh = {
        col: (stk[col].quantile(0.9) if bool(stk[col].notna().any()) else None)
        for _, col in WINDOWS
    }
    idx_by_sec = {r["sector_name"]: r for _, r in idx.iterrows()}

    cards, breadth, deep = [], [], []
    for sec, g in stk.groupby("sector", sort=True):
        if sec not in idx_by_sec:
            continue  # sector with constituents but no mapped index → not a board sector
        ir = idx_by_sec[sec]
        n = len(g)
        f = _num

        def rel(w, ir=ir):  # RS vs Nifty 500, fraction
            a, b = _num(ir[w]), _num(n500.get(w))
            return a - b if (a is not None and b is not None) else None

        pct_ema21 = round(float(g["above_ema_21"].mean()), 4)
        pct_ema50 = round(float(g["above_ema_50"].mean()), 4)
        pct_ema200 = round(float(g["above_ema_200"].mean()), 4)
        pct_52wh = round(float((g["pos_52w"] >= 95).mean()), 4)
        strength = _quintile_counts(pd.Series(g["ret_3m"]))
        leaders = int((g["d_comp"] == 10).sum())
        tiers = g["conviction_tier"].fillna("")
        conf = {
            "H": int(tiers.isin(STRONG_TIER).sum()),
            "M": int(tiers.isin(MED_TIER).sum()),
            "L": int((~tiers.isin(STRONG_TIER + MED_TIER)).sum()),
        }
        verdict, abbr = verdicts[sec]

        cards.append(
            {
                "as_of_date": as_of,
                "sector_name": sec,
                "constituent_count": n,
                "ret_1w": f(ir["ret_1w"]),
                "ret_1m": f(ir["ret_1m"]),
                "ret_3m": f(ir["ret_3m"]),
                "ret_6m": f(ir["ret_6m"]),
                "ret_12m": f(ir["ret_12m"]),
                "rs_1m": rel("ret_1m"),
                "rs_3m": rel("ret_3m"),
                "rs_6m": rel("ret_6m"),
                "vol_60d_ann": None,  # not rendered by any live component — left NULL, not fabricated
                "pct_above_ema21": pct_ema21,
                "pct_above_ema200": pct_ema200,
                "pct_at_52wh": pct_52wh,
                "hhi_concentration": None,  # not rendered — left NULL
                "buy_signal_count": leaders,
                "confidence_distribution": json.dumps(conf),
                "verdict": verdict,
                "verdict_abbr": abbr,
                "refreshed_at": now,
            }
        )

        by_window = []
        for label, col in WINDOWS:
            r = g[col].dropna()
            thr = dec_thresh[col]
            by_window.append(
                {
                    "window": label,
                    "pct_positive": round(float((r > 0).mean()), 4) if len(r) else None,
                    "pct_top_decile_movers": round(float((r >= thr).mean()), 4)
                    if (len(r) and thr is not None)
                    else None,
                }
            )
        breadth.append(
            {
                "as_of_date": as_of,
                "sector_name": sec,
                "constituent_count": n,
                "pct_above_ema21": pct_ema21,
                "pct_above_ema50": pct_ema50,
                "pct_above_ema200": pct_ema200,
                "pct_at_52wh": pct_52wh,
                "breadth_by_window": json.dumps(by_window),
                "breadth_by_strength": json.dumps(strength),
                "top_movers": json.dumps(_movers(g, "ret_1m", top=True)),
                "bottom_movers": json.dumps(_movers(g, "ret_1m", top=False)),
                "refreshed_at": now,
            }
        )

        pctf = lambda x: round(x * 100, 2) if x is not None else None  # frac→percent
        deep.append(
            {
                "sector_name": sec,
                "verdict": verdict,
                "constituent_count": n,
                "data_as_of": as_of,
                "returns": json.dumps(
                    {
                        "ret_1w": pctf(f(ir["ret_1w"])),
                        "ret_1m": pctf(f(ir["ret_1m"])),
                        "ret_3m": pctf(f(ir["ret_3m"])),
                        "ret_6m": pctf(f(ir["ret_6m"])),
                        "ret_12m": pctf(f(ir["ret_12m"])),
                    }
                ),
                "rs_windows": json.dumps(
                    {
                        "rs_1w": None,
                        "rs_1m": pctf(rel("ret_1m")),
                        "rs_3m": pctf(rel("ret_3m")),
                        "rs_6m": pctf(rel("ret_6m")),
                        "rs_12m": None,
                    }
                ),
                "pct_above_ema21": pct_ema21,
                "pct_above_ema200": pct_ema200,
                "pct_at_52wh": pct_52wh,
                "constituents_top30": json.dumps(
                    []
                ),  # constituent table sources getSectorStocks, not this
                "open_signals": json.dumps([]),  # M5 signal-call methodology retired
                "strength_dist": json.dumps(strength),
                "top_picks_top10": json.dumps([]),  # top-picks panel removed (FM 2026-06-26)
                "refreshed_at": now,
            }
        )

    cards_df, breadth_df, deep_df = pd.DataFrame(cards), pd.DataFrame(breadth), pd.DataFrame(deep)
    _ensure_unique_index("mv_sector_cards", ["as_of_date", "sector_name"], "ux_mv_sector_cards")
    _ensure_unique_index("mv_sector_breadth", ["as_of_date", "sector_name"], "ux_mv_sector_breadth")
    _ensure_unique_index("mv_sector_deepdive", ["sector_name"], "ux_mv_sector_deepdive")
    # deepdive is latest-only (single row per sector, no as_of key) — clear then insert.
    _db.exec_sql(f"delete from {M}.mv_sector_deepdive")
    nc = _db.upsert_df(f"{M}.mv_sector_cards", cards_df, ["as_of_date", "sector_name"])
    nb = _db.upsert_df(f"{M}.mv_sector_breadth", breadth_df, ["as_of_date", "sector_name"])
    nd = _db.upsert_df(f"{M}.mv_sector_deepdive", deep_df, ["sector_name"])

    # self-check: the getSectorCards anchor requires non-null rs_1m AND ret_1w, else the
    # sectors page renders nothing. Fail loudly here rather than blank the board.
    anchored = cards_df[cards_df["rs_1m"].notna() & cards_df["ret_1w"].notna()]
    assert len(anchored) == len(cards_df), (
        "cards missing rs_1m/ret_1w — sectors page anchor would drop them"
    )
    assert nc == nb == nd, f"row-count mismatch cards={nc} breadth={nb} deep={nd}"
    print(f"[sector_cards] as_of={as_of} (tech={tech_asof}) sectors={nc}")
    print(f"[sector_cards] verdicts: {cards_df['verdict'].value_counts().to_dict()}")
    print(
        cards_df[
            ["sector_name", "ret_3m", "rs_3m", "pct_above_ema21", "buy_signal_count", "verdict"]
        ].to_string(index=False)
    )


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
