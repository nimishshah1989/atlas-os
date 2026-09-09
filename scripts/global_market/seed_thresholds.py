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
  India's rows, ported (docs/superpowers/plans/2026-08-23-stock-universe-liquidity-floor.md) —
  and, since 2026-09-06, ``liquidity_min_traded_value_usd`` $1,000,000. That last row is NOT a
  ported number and NOT a guess: the plan's process was "Phase 1 prints the ADV$ table so the FM
  sets the floor from data", P1-E printed it (``docs/global/reports/adv_usd_2026-09-03.md``), and
  the FM read the real distribution and chose. ONE floor serves both asset classes because all
  503 S&P 500 members on that date clear it. The refusal path in ``build_universe_snapshot``
  stays exactly as it was — it is the guard for any database where the row is missing or
  inactive, not a placeholder waiting for this seed.
* P3-A fundamentals: ``fund_min_quarters`` 8 — the quarterly history a stock needs before the
  fundamental lens may score it, and the number ``ingest_financials.py`` counts filers against
  every night. Two years is the shortest window carrying a year-on-year growth rate and the
  prior-year comparison it is measured against; it is a COVERAGE floor, not one of the §B
  scoring bands below.

* M2 baskets (category ``basket``, section M2) — the FM's basket instruction of 2026-09-09, the
  numbers India's ``portfolio_*`` rows carry translated to USD and fractional shares:
  ``basket_default_capital_usd`` $100,000 (the builder's default and floor),
  ``basket_max_position_pct`` 0.25 (no constituent above a quarter of capital),
  ``basket_cost_bps_buy`` / ``basket_cost_bps_sell`` 0 bps (paper baskets: no execution cost
  until an execution provider names one), ``basket_min_weight_frac`` 0.01 (a name below 1
  percent is noise, not a position). Read by ``mark_baskets.py``, ``validate_baskets.py`` and
  the board's basket builder; none of them carries a fallback.

NOT seeded, on purpose:
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
import pandas as pd
import psycopg2
from _financials import financial_ids, financial_metrics

from atlas.global_market.fundamentals import bands
from atlas.global_market.fundamentals import cross_section as xsec
from atlas.global_market.scoring.stock_lenses import REACHABLE_KEYS

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
         "Catalyst bucket weight: earnings and strategy (8-K 2.02, 1.01, 1.02, 2.01, 2.05, 2.06). "
         "NOT 8.01: Other Events says only that something happened, and reading it needs a parser "
         "of the attached press release, which is the keyword-matching this lens avoids"),
    _row("catalyst_w_capital", "0.30", "catalyst", "B", "weight", "0", "1",
         "Catalyst bucket weight: capital action (8-K 2.03, 2.04, 3.02, 3.03, 5.01). NOT dividends "
         "or buybacks: neither has an item code — both arrive as a press release on an 8.01"),
    _row("catalyst_w_governance", "0.15", "catalyst", "B", "weight", "0", "1",
         "Catalyst bucket weight: governance and distress (8-K 1.03, 3.01, 4.01, 4.02, 5.02)"),
    _row("catalyst_recency_t1", "90", "catalyst", "B", "days", "1", "3650",
         "News this old or newer keeps catalyst_decay_t1 of its points"),
    _row("catalyst_recency_t2", "180", "catalyst", "B", "days", "1", "3650",
         "News this old or newer keeps catalyst_decay_t2 of its points"),
    _row("catalyst_recency_t3", "365", "catalyst", "B", "days", "1", "3650",
         "The catalyst lens's whole lookback: older news keeps catalyst_decay_old. "
         "ingest_filings_8k.py reads this row to decide whose SEC feed is too shallow to score "
         "over — filings.recent is capped by COUNT, so a heavy filer's 8-K history is short"),
    # ── §B flow lens + risk flags ─────────────────────────────────────────────────────────
    _row("flow_si_extreme_pct", "20", "flow", "B", "percent", "0", "100",
         "Short interest above this percent of float raises the risk flag. NOT read by the flow "
         "lens: nothing in atlas_global carries a float, and inferring one would be a derived "
         "number wearing a real one's clothes. The lens uses days to cover instead"),
    # ── §B flow lens on FINRA short interest (stock_flow.py) ──────────────────────────────
    # plan.md orders this lens "Form 4 first". The census in tests/fixtures/global/form4/SOURCE.md
    # measured what that gives: zero open-market purchases in a year across three megacaps, and
    # every sale under a 10b5-1 plan adopted months earlier. Short interest is dense, free and
    # nine years deep, so it goes first; Form 4 stays worth adding as a sparse overlay.
    _row("flow_si_max_age_days", "45", "flow", "B", "days", "1", "365",
         "The newest settlement may be at most this old or the lens refuses to score. FINRA "
         "publishes ~8 business days after a twice-monthly settlement, so a fresh reading is "
         "routinely three weeks old; beyond this it is last quarter's positioning, not today's"),
    _row("flow_dtc_low", "2", "flow", "B", "days", "0", "100",
         "Days to cover at or below this is an uncrowded short — the best rung"),
    _row("flow_dtc_ok", "4", "flow", "B", "days", "0", "100",
         "Days to cover at or below this is ordinary"),
    _row("flow_dtc_high", "8", "flow", "B", "days", "0", "100",
         "Days to cover at or below this is crowded; beyond it is the extreme rung"),
    _row("flow_dtc_pts_low", "10", "flow", "B", "points", "-50", "50",
         "Points from 50 when days to cover is at or below flow_dtc_low"),
    _row("flow_dtc_pts_ok", "4", "flow", "B", "points", "-50", "50",
         "Points when days to cover is at or below flow_dtc_ok"),
    _row("flow_dtc_pts_high", "-6", "flow", "B", "points", "-50", "50",
         "Points when days to cover is at or below flow_dtc_high"),
    _row("flow_dtc_pts_extreme", "-14", "flow", "B", "points", "-50", "50",
         "Points beyond flow_dtc_high. UNEXERCISED by the committed fixtures — three healthy "
         "megacaps are never crowded shorts — so its size is the least evidenced number here"),
    _row("flow_si_change_big", "20", "flow", "B", "percent", "0", "500",
         "A move of this size in the short position since the last settlement is a big one"),
    _row("flow_si_change_mod", "8", "flow", "B", "percent", "0", "500",
         "A move of this size is a moderate one; smaller is flat"),
    _row("flow_si_pts_covering_big", "8", "flow", "B", "points", "-50", "50",
         "Points when the short position fell by flow_si_change_big or more — shorts covering"),
    _row("flow_si_pts_covering_mod", "4", "flow", "B", "points", "-50", "50",
         "Points when the short position fell by flow_si_change_mod or more"),
    _row("flow_si_pts_building_mod", "-4", "flow", "B", "points", "-50", "50",
         "Points when the short position rose by flow_si_change_mod or more. Gentler than the "
         "level ladder on purpose: convertible, index and merger arbitrage all short against a "
         "hedge, so a rising position is not necessarily a bearish view"),
    _row("flow_si_pts_building_big", "-8", "flow", "B", "points", "-50", "50",
         "Points when the short position rose by flow_si_change_big or more"),
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
    # ── Universe (universe_core.members predicate) ────────────────────────────────────────
    _row("liquidity_min_observations_60d", "40", "universe", "universe", "sessions", "1", "60",
         "Minimum traded sessions in the 60-session window for a valid median"),
    _row("liquidity_recency_trading_days", "5", "universe", "universe", "sessions", "1", "60",
         "Latest trade must be within this many sessions of the window end"),
    _row("liquidity_min_traded_value_usd", "1000000", "universe", "universe", "usd", "0",
         USD_CEILING,
         "ADV$ floor for scoring and basket eligibility. FM decision 2026-09-06, read off the "
         "REAL distribution in docs/global/reports/adv_usd_2026-09-03.md (2,114 of 5,656 ETFs "
         "clear $1M; so do all 503 S&P 500 members, so one floor serves both asset classes)"),
    # ── P2-C: the POINT VALUES the ETF lens sub-scores award (docs/global/phase2.md) ────────
    # The bands above say WHERE a fund falls; these say what that is worth. Both belong in the
    # table for the same reason: the FM re-tunes a ladder from /admin without a deploy, and a
    # score nobody can trace to a row is a score nobody should act on (rule #4).
    _row("etf_quintile_q1_pts", "25", "etf_scoring", "C", "points", "0", "25",
         "Top-quintile points on any percentile sub-score (peer RS, vol, drawdown, expense)"),
    _row("etf_quintile_q2_pts", "20", "etf_scoring", "C", "points", "0", "25",
         "Second-quintile points on any percentile sub-score"),
    _row("etf_quintile_q3_pts", "15", "etf_scoring", "C", "points", "0", "25",
         "Middle-quintile points on any percentile sub-score"),
    _row("etf_quintile_q4_pts", "10", "etf_scoring", "C", "points", "0", "25",
         "Fourth-quintile points on any percentile sub-score"),
    _row("etf_quintile_q5_pts", "5", "etf_scoring", "C", "points", "0", "25",
         "Bottom-quintile points on any percentile sub-score"),
    _row("etf_rs_spy_3m_pts", "8", "etf_scoring", "C", "points", "0", "25",
         "Points when 3-month RS vs SPY clears rs_spy_strong"),
    _row("etf_rs_spy_6m_pts", "8", "etf_scoring", "C", "points", "0", "25",
         "Points when 6-month RS vs SPY clears rs_spy_strong"),
    _row("etf_rs_spy_12m_pts", "9", "etf_scoring", "C", "points", "0", "25",
         "Points when 12-month RS vs SPY clears rs_spy_strong (the three sum to 25)"),
    _row("etf_rs_spy_partial_frac", "0.5", "etf_scoring", "C", "fraction", "0", "1",
         "Fraction of a window's points for beating SPY but not by rs_spy_strong"),
    _row("etf_risk_beta_t1_pts", "25", "etf_scoring", "C", "points", "0", "25",
         "Beta band 1 points (beta <= risk_beta_t1)"),
    _row("etf_risk_beta_t2_pts", "18", "etf_scoring", "C", "points", "0", "25",
         "Beta band 2 points"),
    _row("etf_risk_beta_t3_pts", "10", "etf_scoring", "C", "points", "0", "25",
         "Beta band 3 points"),
    _row("etf_risk_beta_t4_pts", "3", "etf_scoring", "C", "points", "0", "25",
         "Beta band 4 points (above risk_beta_t3)"),
    _row("etf_cost_adv_t1_pts", "25", "etf_scoring", "C", "points", "0", "25",
         "ADV$/AUM band 1 points (at or above cost_adv_usd_t1 / cost_aum_usd_t1)"),
    _row("etf_cost_adv_t2_pts", "20", "etf_scoring", "C", "points", "0", "25",
         "ADV$/AUM band 2 points"),
    _row("etf_cost_adv_t3_pts", "15", "etf_scoring", "C", "points", "0", "25",
         "ADV$/AUM band 3 points"),
    _row("etf_cost_adv_t4_pts", "10", "etf_scoring", "C", "points", "0", "25",
         "ADV$/AUM band 4 points"),
    _row("etf_cost_adv_t5_pts", "3", "etf_scoring", "C", "points", "0", "25",
         "ADV$/AUM below every band"),
    # ── M2 baskets (mark_baskets.py, validate_baskets.py, the board's basket builder) ─────
    _row("basket_default_capital_usd", "100000", "basket", "M2", "usd", "1", USD_CEILING,
         "Starting capital a new basket is booked with, and the floor the builder accepts"),
    _row("basket_max_position_pct", "0.25", "basket", "M2", "fraction", "0", "1",
         "No constituent may exceed this fraction of capital at inception (position cap)"),
    _row("basket_cost_bps_buy", "0", "basket", "M2", "bps", "0", "10000",
         "Execution cost on a buy, basis points of value; 0 until an execution provider names one"),
    _row("basket_cost_bps_sell", "0", "basket", "M2", "bps", "0", "10000",
         "Execution cost on a sell, basis points of value; 0 until an execution provider names one"),
    _row("basket_min_weight_frac", "0.01", "basket", "M2", "fraction", "0", "1",
         "Smallest target weight a constituent may carry (below it a name is noise, not a position)"),
    # ── P3-A company fundamentals (ingest_financials.py → stock_financials_pit) ───────────
    # ── §B catalyst lens: bucket weights, decay, and one row per SEC 8-K item code ─────────
    # These ARE written down, unlike the fundamental bands, because they are not percentiles of
    # anything: they are the FM's opinion of what a filing is worth. plan.md §B's figures where
    # it names one; the rest follow its shape — distress costs more than good news pays, because
    # a bankruptcy is a fact about the future and a results filing is a fact about the past.
    _row("catalyst_decay_t1", "1.0", "catalyst", "B", "multiple", "0", "1",
         "Share of an event's points surviving inside catalyst_recency_t1"),
    _row("catalyst_decay_t2", "0.8", "catalyst", "B", "multiple", "0", "1",
         "Share surviving between t1 and catalyst_recency_t2"),
    _row("catalyst_decay_t3", "0.5", "catalyst", "B", "multiple", "0", "1",
         "Share surviving between t2 and catalyst_recency_t3"),
    _row("catalyst_decay_old", "0.3", "catalyst", "B", "multiple", "0", "1",
         "Share surviving beyond catalyst_recency_t3"),
    # Points per 8-K item code. The key is the code with its dot as an underscore
    # (stock_catalyst.points_key), and the scorer reads NOTHING it cannot find here.
    _row("catalyst_pts_2_02", "6", "catalyst", "B", "points", "-50", "50",
         "8-K 2.02 Results of Operations and Financial Condition — the company reported"),
    _row("catalyst_pts_1_01", "10", "catalyst", "B", "points", "-50", "50",
         "8-K 1.01 Entry into a Material Definitive Agreement"),
    _row("catalyst_pts_1_02", "-6", "catalyst", "B", "points", "-50", "50",
         "8-K 1.02 Termination of a Material Definitive Agreement"),
    _row("catalyst_pts_2_01", "8", "catalyst", "B", "points", "-50", "50",
         "8-K 2.01 Completion of an Acquisition or Disposition of Assets"),
    _row("catalyst_pts_2_05", "-6", "catalyst", "B", "points", "-50", "50",
         "8-K 2.05 Costs Associated with Exit or Disposal Activities"),
    _row("catalyst_pts_2_06", "-10", "catalyst", "B", "points", "-50", "50",
         "8-K 2.06 Material Impairments"),
    _row("catalyst_pts_2_03", "-4", "catalyst", "B", "points", "-50", "50",
         "8-K 2.03 Creation of a Direct Financial Obligation"),
    _row("catalyst_pts_2_04", "-12", "catalyst", "B", "points", "-50", "50",
         "8-K 2.04 Triggering Events That Accelerate a Direct Financial Obligation"),
    _row("catalyst_pts_3_02", "-8", "catalyst", "B", "points", "-50", "50",
         "8-K 3.02 Unregistered Sales of Equity Securities — dilution"),
    _row("catalyst_pts_3_03", "-3", "catalyst", "B", "points", "-50", "50",
         "8-K 3.03 Material Modification to Rights of Security Holders"),
    _row("catalyst_pts_5_01", "-5", "catalyst", "B", "points", "-50", "50",
         "8-K 5.01 Changes in Control of Registrant"),
    _row("catalyst_pts_1_03", "-25", "catalyst", "B", "points", "-50", "50",
         "8-K 1.03 Bankruptcy or Receivership — the heaviest single event on the form"),
    _row("catalyst_pts_3_01", "-15", "catalyst", "B", "points", "-50", "50",
         "8-K 3.01 Notice of Delisting or Failure to Satisfy a Continued Listing Rule"),
    _row("catalyst_pts_4_01", "-12", "catalyst", "B", "points", "-50", "50",
         "8-K 4.01 Changes in the Registrant's Certifying Accountant"),
    _row("catalyst_pts_4_02", "-15", "catalyst", "B", "points", "-50", "50",
         "8-K 4.02 Non-Reliance on Previously Issued Financial Statements — a restatement"),
    _row("catalyst_pts_5_02", "-8", "catalyst", "B", "points", "-50", "50",
         "8-K 5.02 Departure or Election of Directors or Certain Officers"),
    _row("fund_min_quarters", "8", "fundamental", "B", "quarters", "1", "40",
         "Quarterly filings a stock needs before the fundamental lens may score it. 8 = two "
         "years, which is the shortest window that carries a year-on-year growth rate AND the "
         "prior-year comparison it is measured against. P3-A's definition of done reads this "
         "row: >=95% of S&P 500 members at or above it. ingest_financials.py counts filers "
         "below it every night and refuses to run if this row is missing"),
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


# ── the fundamental bands, cut from the index's own distribution ────────────────────────────
#
# These are the only seeds NOT written down in this file, and they cannot be: India's ladder
# starts at ROE 20 because that is where India's index sits, and a ladder whose rungs all sit
# below the S&P 500 puts every name on the top rung — the sub-score stops discriminating and the
# board reads "these companies are all excellent" rather than "this measure is switched off".
# plan.md §B: "seeded from the actual S&P 500 cross-sectional quartiles on the first run".
#
# So they are DERIVED, by the stated formula in atlas.global_market.fundamentals.bands, over the
# real assembled filings in stock_financials_pit — a computation over real data, printed in full
# before it is written, and seeded (never overwriting a value the FM has tuned).

#: (units, min, max) per metric, for the admin panel's clamps. Rates arrive in PER CENT from
#: cross_section; the ratios are plain multiples.
_BAND_BOUNDS: dict[str, tuple[str, str, str]] = {
    "roe": ("percent", "-200", "200"),
    "roce": ("percent", "-200", "200"),
    "operating_margin": ("percent", "-200", "200"),
    "net_margin": ("percent", "-200", "200"),
    "revenue_growth": ("percent", "-100", "500"),
    "eps_growth": ("percent", "-100", "500"),
    "debt_to_equity": ("ratio", "0", "50"),
    "current_ratio": ("ratio", "0", "50"),
}

_BAND_METRIC: dict[str, str] = {
    key: metric for metric, _d, rungs in bands.LADDERS for key, _p in rungs
}
_BAND_PERCENTILE: dict[str, int] = {
    key: pct for _m, _d, rungs in bands.LADDERS for key, pct in rungs
}


def fundamental_band_rows(table: pd.DataFrame, anchor: str) -> list[dict[str, object]]:
    """The derived fundamental bands as seed rows, each saying which percentile it is.

    A threshold whose description does not say where it came from is a number the FM cannot
    argue with, so every row names its metric, its percentile, the population size and the
    session — the four things needed to reproduce it.
    """
    derived = bands.bands_from_cross_section(table)
    names = {str(r["metric"]): int(r["names"]) for r in table.to_dict("records")}
    out: list[dict[str, object]] = []
    for key, value in sorted(derived.items()):
        metric = _BAND_METRIC[key]
        units, lo, hi = _BAND_BOUNDS[metric]
        out.append(
            _row(
                key,
                str(value),
                "fundamental",
                "B",
                units,
                lo,
                hi,
                f"P{_BAND_PERCENTILE[key]} of {metric} across {names.get(metric, 0)} S&P 500 "
                f"members with a full trailing-twelve-month window at EOD {anchor}. Cut from the "
                f"index's own distribution because India's ladder describes India's index; edit "
                f"it here and the lens re-scores on the next run",
            )
        )
    return out


def check_seeds(rows: list[dict[str, object]]) -> None:
    """Internal consistency of the seed table itself (keys unique, weights sum to 1)."""
    keys = [str(r["threshold_key"]) for r in rows]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate seed keys: {sorted(dupes)}"
    for prefix in ("lens_weight_", "etf_lens_weight_"):
        weights = [r for r in rows if str(r["threshold_key"]).startswith(prefix)]
        if not weights:
            continue  # a bands-only run carries no weights; only a FULL set must sum to one
        total = sum(Decimal(str(r["threshold_value"])) for r in weights)
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
    ap.add_argument(
        "--fundamental-bands",
        action="store_true",
        help="ALSO cut the 34 reachable fundamental bands from the live S&P 500 cross-section "
        "(reads stock_financials_pit; prints the whole ladder before writing)",
    )
    args = ap.parse_args(argv)

    rows = list(SEEDS)
    if args.fundamental_bands:
        rows += band_rows_from_prod()

    check_seeds(rows)
    if args.dry_run:
        print_table(rows)
        return 0

    dsn = _gdb.psycopg2_url()
    print(f"target {dsn.rsplit('@', 1)[-1]}  table {_gdb.M}.atlas_thresholds")
    try:
        inserted, present = seed(rows, dsn)
    except psycopg2.Error as e:
        print(f"FAILED (rolled back): {e}", file=sys.stderr)
        return 1
    print(f"inserted {inserted}, already present {present} (left untouched)")
    return 0


def band_rows_from_prod() -> list[dict[str, object]]:
    """Assemble the index's fundamentals at the latest session and cut the ladder from them.

    Prints the cross-section it cut from AND the ladder it produced: a threshold nobody watched
    being derived is a threshold nobody can check.
    """
    # The SAME anchor score_stocks uses: the latest technical_daily session at or before the
    # EOD cutoff. Cutting the ladder on a different session from the one the lens is scored on
    # would set the market's methodology from a population the scorer never sees.
    anchor = _gdb.read_df(
        f"SELECT max(date) AS d FROM {_gdb.M}.technical_daily WHERE date <= :cutoff",
        {"cutoff": _gdb.eod_cutoff()},
    )["d"].iloc[0]
    if anchor is None:
        print("technical_daily is empty — run compute_technicals.py first", file=sys.stderr)
        return []
    metrics = financial_metrics(anchor, financial_ids())
    table = xsec.cross_section(metrics.values())
    print(f"\n[seed_thresholds] S&P 500 fundamental cross-section at EOD {anchor}")
    print(table.to_string(index=False))
    rows = fundamental_band_rows(table, str(anchor))
    print(f"[seed_thresholds] cut {len(rows)} band(s) from it")
    undecided = bands.undecidable(REACHABLE_KEYS)
    if undecided:
        print(f"  NOT derivable and NOT required: {sorted(undecided)}")
    return rows


if __name__ == "__main__":
    sys.exit(main())
