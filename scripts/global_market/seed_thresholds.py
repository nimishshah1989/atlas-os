#!/usr/bin/env python3
"""Seed atlas_global.atlas_thresholds with the plan's STARTING values (Methodology §B / §C).

FM APPROVAL IS REQUIRED BEFORE THIS RUNS — do not execute it on prod until the FM has read
the ``--dry-run`` table and said yes. The no-hardcoded-methodology-numbers rule is why the
values live in ``atlas_thresholds`` and not in code; rule #0 is why they must be understood as
INPUTS the FM owns, not conclusions the code reached: a lens keeps its seed weight only after
the IC report (§E) shows it carries signal on the full backfill, and the FM locks the final
weights from ``/admin/thresholds``. Every row here is a transcription of a number written in
the approved plan (``docs/global/plan.md``) or in India's documented threshold rows; a key
the plan names WITHOUT a value is deliberately absent, so the step that needs it fails loudly
until the FM supplies one.

What is seeded (each row: key, value, category, description, units, min, max, default = value):

* §B stocks — composite weights (technical 0.30 / fundamental 0.30 / catalyst 0.25 / flow 0.15;
  lighter flow than India because US flow is thinner at launch), conviction tiers with India's
  key names (70/3, 58/2, 45, 30), the verbatim technical-scorer keys, catalyst bucket weights
  (0.55 / 0.30 / 0.15) + recency windows (90 / 180 / 365 d), short-interest extreme (20 %),
  risk-flag degradation floor (−30).
* §C ETFs — lens weights (technical 0.35 / risk 0 / cost-liquidity 0.20 / flow 0.15 /
  quality 0.30), ``rs_spy_strong`` 0.05, ``peer_group_min_members`` 8, ADV$ / AUM / top-10
  cut-offs, Δ-shares bands, beta bands, ``etf_lookthrough_min_coverage`` 0.60,
  ``quality_w_composite`` 0.7 / ``quality_w_leaders`` 0.3.
* §D ``rollup_breadth_min`` 60 · §E ``ic_floor_{1m,3m,6m,12m}`` 0.02 / 0.04 / 0.05 / 0.04.
* Universe: ``liquidity_min_observations_60d`` 40 and ``liquidity_recency_trading_days`` 5 —
  India's rows, ported (docs/superpowers/plans/2026-08-23-stock-universe-liquidity-floor.md).

NOT seeded, on purpose:
* ``liquidity_min_traded_value_usd`` — the plan has the FM set the floor from the REAL ADV$
  distribution ``build_universe_snapshot`` prints in Phase 1; ``universe_core.members`` reads
  the key, so with no row the universe step fails instead of cutting on an invented floor.
* ``cls_country_pure_min_weight``, ``cls_country_equity_min``, ``cls_sector_pure_min``,
  ``cls_llm_min_confidence`` — the plan names the keys and leaves the values to Phase 2
  (risk #10: country-product semantics are locked with the FM then). Seeding a guess would
  make an invented number FM-approved by default.
* fundamental / valuation bands (§B: seeded from the live S&P 500 cross-section on the first
  run — India's numbers are wrong for this index), ETF-specific conviction tiers (values not
  fixed in the plan), per-event catalyst points and the flow insider / 13F ladders (key names
  not fixed in the plan). Those land with their lens modules.

Writes are ``INSERT … ON CONFLICT (threshold_key) DO NOTHING`` — re-running never overwrites
an FM edit; delete a row deliberately if a seed must be re-issued.

    python scripts/global_market/seed_thresholds.py --dry-run   # print the table, write nothing
    python scripts/global_market/seed_thresholds.py             # insert missing rows
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

import _gdb
import psycopg2

MODIFIED_BY = "seed_thresholds.py"

# atlas_thresholds.* columns are numeric(18,6): the largest whole-dollar value they can hold.
# max_allowed for every USD key (SPY's AUM alone is in the hundreds of billions).
USD_CEILING = "999999999999"
NUMERIC_18_6_LIMIT = Decimal(10) ** 12


def _row(
    key: str,
    value: str,
    category: str,
    section: str,
    units: str,
    lo: str,
    hi: str,
    description: str,
) -> dict[str, object]:
    return {
        "threshold_key": key,
        "threshold_value": Decimal(value),
        "category": category,
        "description": description,
        "methodology_section": section,
        "units": units,
        "min_allowed": Decimal(lo),
        "max_allowed": Decimal(hi),
        "default_value": Decimal(value),
    }


# A data table — one seed per entry: (key, value, category, section, units, min, max, description).
# Kept in the tabular layout on purpose; the formatter would spread each row over ten lines.
# fmt: off
SEEDS: list[dict[str, object]] = [
    # ── §B stock composite weights (renormalised over PRESENT lenses in blend()) ──────────
    _row("lens_weight_technical", "0.30", "lens_weight", "B", "weight", "0", "1",
         "Stock composite weight of the technical lens (seed; IC decides)"),
    _row("lens_weight_fundamental", "0.30", "lens_weight", "B", "weight", "0", "1",
         "Stock composite weight of the fundamental lens (seed; IC decides)"),
    _row("lens_weight_catalyst", "0.25", "lens_weight", "B", "weight", "0", "1",
         "Stock composite weight of the catalyst lens (seed; IC decides)"),
    _row("lens_weight_flow", "0.15", "lens_weight", "B", "weight", "0", "1",
         "Stock composite weight of the flow lens — lighter than India at launch (Form 4 only)"),
    # ── §B conviction tiers (India key names, so nest_thresholds() works unchanged) ───────
    _row("lens_conviction_highest_score", "70", "conviction", "B", "score", "0", "100",
         "HIGHEST tier: composite >= this"),
    _row("lens_conviction_highest_min_layers", "3", "conviction", "B", "count", "1", "4",
         "HIGHEST tier: minimum lenses present"),
    _row("lens_conviction_high_score", "58", "conviction", "B", "score", "0", "100",
         "HIGH tier: composite >= this"),
    _row("lens_conviction_high_min_layers", "2", "conviction", "B", "count", "1", "4",
         "HIGH tier: minimum lenses present"),
    _row("lens_conviction_medium_score", "45", "conviction", "B", "score", "0", "100",
         "MEDIUM tier: composite >= this"),
    _row("lens_conviction_watch_score", "30", "conviction", "B", "score", "0", "100",
         "WATCH tier: composite >= this; below is BELOW_THRESHOLD"),
    # ── §B technical lens (score_technical verbatim) ──────────────────────────────────────
    _row("ema_aligned_all", "10", "technical", "B", "points", "0", "25",
         "Trend sub-score points when EMA21 > EMA50 > EMA200"),
    _row("ema_aligned_partial", "6", "technical", "B", "points", "0", "25",
         "Trend sub-score points for partial EMA alignment"),
    _row("price_above_ema200_strong", "0.05", "technical", "B", "fraction", "-1", "1",
         "Price vs EMA200 above this fraction scores the strong band"),
    _row("price_below_ema200_weak", "-0.05", "technical", "B", "fraction", "-1", "1",
         "Price vs EMA200 below this fraction scores the weak band"),
    _row("slope_strong_pct", "0.02", "technical", "B", "fraction", "-1", "1",
         "EMA-21 slope proxy (ret_1w) above this scores the strong band"),
    _row("slope_weak_pct", "-0.02", "technical", "B", "fraction", "-1", "1",
         "EMA-21 slope proxy (ret_1w) below this scores the weak band"),
    _row("rs_golden_cross_pts", "10", "technical", "B", "points", "0", "25",
         "RS-structure points when EMA50 > EMA200"),
    _row("rs_fast_above_mid_pts", "15", "technical", "B", "points", "0", "25",
         "RS-structure points when EMA21 > EMA50"),
    # ── §B catalyst lens (stock_catalyst.py; India's 3-bucket shape and decay) ────────────
    _row("catalyst_w_earnings", "0.55", "catalyst", "B", "weight", "0", "1",
         "Catalyst bucket weight: earnings / strategy (8-K 2.02, 1.01, 2.01, 8.01)"),
    _row("catalyst_w_capital", "0.30", "catalyst", "B", "weight", "0", "1",
         "Catalyst bucket weight: capital action (dividends, buybacks, offerings, 3.02)"),
    _row("catalyst_w_governance", "0.15", "catalyst", "B", "weight", "0", "1",
         "Catalyst bucket weight: governance (4.01, 5.02, 4.02, 3.01, 1.03, NT 10-K/Q)"),
    _row("catalyst_recency_t1", "90", "catalyst", "B", "days", "1", "1000",
         "Recency window 1: full weight up to this many days"),
    _row("catalyst_recency_t2", "180", "catalyst", "B", "days", "1", "1000",
         "Recency window 2: second decay step ends here"),
    _row("catalyst_recency_t3", "365", "catalyst", "B", "days", "1", "1000",
         "Recency window 3: third decay step ends here (older events carry the tail weight)"),
    # ── §B flow lens + risk flags ─────────────────────────────────────────────────────────
    _row("flow_si_extreme_pct", "20", "flow", "B", "percent", "0", "100",
         "Short interest above this % of float raises the risk flag"),
    _row("degradation_floor", "-30", "risk", "B", "points", "-100", "0",
         "Floor of the stored (not applied) degradation overlay"),
    # ── §C ETF lens weights (renormalised over present lenses; risk = overlay until FM sets) ─
    _row("etf_lens_weight_technical", "0.35", "etf_lens_weight", "C", "weight", "0", "1",
         "ETF composite weight of the technical lens (seed)"),
    _row("etf_lens_weight_risk", "0", "etf_lens_weight", "C", "weight", "0", "1",
         "ETF composite weight of the risk lens — 0 = overlay until the FM sets one"),
    _row("etf_lens_weight_cost_liquidity", "0.20", "etf_lens_weight", "C", "weight", "0", "1",
         "ETF composite weight of the cost & liquidity lens (seed)"),
    _row("etf_lens_weight_flow", "0.15", "etf_lens_weight", "C", "weight", "0", "1",
         "ETF composite weight of the flow lens (seed; absent without a shares series)"),
    _row("etf_lens_weight_quality", "0.30", "etf_lens_weight", "C", "weight", "0", "1",
         "ETF composite weight of the quality / look-through lens (seed)"),
    # ── §C ETF technical ──────────────────────────────────────────────────────────────────
    _row("rs_spy_strong", "0.05", "etf_technical", "C", "fraction", "0", "1",
         "RS vs SPY (relative form) above this earns the full RS points"),
    _row("peer_group_min_members", "8", "etf_technical", "C", "count", "2", "100",
         "Minimum ETFs in a peer group for within-group percentiles; else the parent group"),
    # ── §C ETF cost & liquidity cut-offs (re-seeded from the live distribution later) ─────
    _row("cost_adv_usd_t1", "50000000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "ADV$ band 1 (top points) starts here"),
    _row("cost_adv_usd_t2", "10000000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "ADV$ band 2 starts here"),
    _row("cost_adv_usd_t3", "2000000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "ADV$ band 3 starts here"),
    _row("cost_adv_usd_t4", "500000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "ADV$ band 4 starts here; below is the floor band"),
    _row("cost_aum_usd_t1", "10000000000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "AUM band 1 (top points) starts here"),
    _row("cost_aum_usd_t2", "1000000000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "AUM band 2 starts here"),
    _row("cost_aum_usd_t3", "250000000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "AUM band 3 starts here"),
    _row("cost_aum_usd_t4", "50000000", "etf_cost", "C", "usd", "0", USD_CEILING,
         "AUM band 4 starts here; below is the floor band"),
    _row("cost_top10_t1", "0.30", "etf_cost", "C", "fraction", "0", "1",
         "Top-10 weight at or below this earns the top concentration points"),
    _row("cost_top10_t2", "0.50", "etf_cost", "C", "fraction", "0", "1",
         "Top-10 weight at or below this earns the second concentration band"),
    _row("cost_top10_t3", "0.70", "etf_cost", "C", "fraction", "0", "1",
         "Top-10 weight at or below this earns the third concentration band"),
    # ── §C ETF flow (Δ shares outstanding, centred at 50) and risk (beta bands) ───────────
    _row("flow_so_t1", "0.02", "etf_flow", "C", "fraction", "0", "1",
         "|Δ shares outstanding| band 1 (±8 points) starts here"),
    _row("flow_so_t2", "0.05", "etf_flow", "C", "fraction", "0", "1",
         "|Δ shares outstanding| band 2 (±15 points) starts here"),
    _row("flow_so_t3", "0.10", "etf_flow", "C", "fraction", "0", "1",
         "|Δ shares outstanding| band 3 (±25 points) starts here"),
    _row("risk_beta_t1", "0.8", "etf_risk", "C", "ratio", "0", "5",
         "Beta to SPY at or below this earns the top beta points (equity ETFs)"),
    _row("risk_beta_t2", "1.0", "etf_risk", "C", "ratio", "0", "5",
         "Beta to SPY at or below this earns the second beta band"),
    _row("risk_beta_t3", "1.3", "etf_risk", "C", "ratio", "0", "5",
         "Beta to SPY at or below this earns the third beta band"),
    # ── §C ETF quality / look-through ─────────────────────────────────────────────────────
    _row("etf_lookthrough_min_coverage", "0.60", "etf_quality", "C", "fraction", "0", "1",
         "Quality lens present only when weight in scored stocks >= this"),
    _row("quality_w_composite", "0.7", "etf_quality", "C", "weight", "0", "1",
         "Quality lens: weight on the holdings-weighted constituent composite"),
    _row("quality_w_leaders", "0.3", "etf_quality", "C", "weight", "0", "1",
         "Quality lens: weight on the share held in Leader stocks"),
    # ── §D roll-ups · §E signal validation ────────────────────────────────────────────────
    _row("rollup_breadth_min", "60", "rollup", "D", "score", "0", "100",
         "Breadth = % members with composite >= this"),
    _row("ic_floor_1m", "0.02", "signal", "E", "ic", "0", "1",
         "A lens keeps its weight only if rank-IC at 1m clears this"),
    _row("ic_floor_3m", "0.04", "signal", "E", "ic", "0", "1",
         "A lens keeps its weight only if rank-IC at 3m clears this"),
    _row("ic_floor_6m", "0.05", "signal", "E", "ic", "0", "1",
         "A lens keeps its weight only if rank-IC at 6m clears this"),
    _row("ic_floor_12m", "0.04", "signal", "E", "ic", "0", "1",
         "A lens keeps its weight only if rank-IC at 12m clears this"),
    # ── Universe (universe_core.members predicate). liquidity_min_traded_value_usd is NOT
    # seeded: the FM sets it from the real ADV$ distribution (see the module docstring). ──
    _row("liquidity_min_observations_60d", "40", "universe", "universe", "sessions", "1", "60",
         "Minimum traded sessions in the 60-session window for a valid median"),
    _row("liquidity_recency_trading_days", "5", "universe", "universe", "sessions", "1", "60",
         "Latest trade must be within this many sessions of the window end"),
]
# fmt: on

_INSERT = f"""
INSERT INTO {_gdb.M}.atlas_thresholds
    (threshold_key, threshold_value, category, description, methodology_section, units,
     min_allowed, max_allowed, default_value, last_modified_by, last_modified_at,
     is_active, created_at)
VALUES
    (%(threshold_key)s, %(threshold_value)s, %(category)s, %(description)s,
     %(methodology_section)s, %(units)s, %(min_allowed)s, %(max_allowed)s,
     %(default_value)s, '{MODIFIED_BY}', now(), true, now())
ON CONFLICT (threshold_key) DO NOTHING
"""


def check_seeds(rows: list[dict[str, object]]) -> None:
    """Internal consistency of the seed table itself (keys unique, weights sum to 1)."""
    keys = [str(r["threshold_key"]) for r in rows]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate seed keys: {sorted(dupes)}"
    for prefix in ("lens_weight_", "etf_lens_weight_"):
        total = sum(
            Decimal(str(r["threshold_value"]))
            for r in rows
            if str(r["threshold_key"]).startswith(prefix)
        )
        assert total == Decimal("1"), f"{prefix}* seeds sum to {total}, expected 1"
    for r in rows:
        v, lo, hi = (Decimal(str(r[c])) for c in ("threshold_value", "min_allowed", "max_allowed"))
        assert lo <= v <= hi, f"{r['threshold_key']}: {v} outside [{lo}, {hi}]"
        for x in (v, lo, hi):  # numeric(18,6) overflows at |x| >= 10^12
            assert abs(x) < NUMERIC_18_6_LIMIT, f"{r['threshold_key']}: {x} overflows numeric(18,6)"
        assert len(str(r["threshold_key"])) <= 64 and len(str(r["category"])) <= 32


def print_table(rows: list[dict[str, object]]) -> None:
    print(
        f"{'threshold_key':34} {'value':>16} {'units':9} {'min':>6} {'max':>16} {'category':16} sec"
    )
    for r in rows:
        print(
            f"{r['threshold_key']!s:34} {r['threshold_value']!s:>16} {r['units']!s:9} "
            f"{r['min_allowed']!s:>6} {r['max_allowed']!s:>16} {r['category']!s:16} "
            f"{r['methodology_section']}"
        )
    print(f"{len(rows)} seed rows")


def seed(rows: list[dict[str, object]], dsn: str) -> tuple[int, int]:
    """Insert missing rows; return (inserted, already_present)."""
    inserted = 0
    conn = psycopg2.connect(dsn)
    try:
        with conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(_INSERT, r)
                inserted += cur.rowcount
    finally:
        conn.close()
    return inserted, len(rows) - inserted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="print the seed table; write nothing")
    args = ap.parse_args(argv)

    check_seeds(SEEDS)
    if args.dry_run:
        print_table(SEEDS)
        return 0

    dsn = _gdb.psycopg2_url()
    print(f"target {dsn.rsplit('@', 1)[-1]}  table {_gdb.M}.atlas_thresholds")
    try:
        inserted, present = seed(SEEDS, dsn)
    except psycopg2.Error as e:
        print(f"FAILED (rolled back): {e}", file=sys.stderr)
        return 1
    print(f"inserted {inserted}, already present {present} (left untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
