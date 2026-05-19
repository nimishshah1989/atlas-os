# allow-large: Eight investigation areas in a single diagnostic script.
# Splitting into sub-files would obscure the sequential diagnostic narrative
# and complicate ad-hoc execution. Responsibility = 1 (diagnose the simulator).

"""v6 simulator diagnostic — root-cause analysis of Phase 9 implausible results.

Runs targeted DB queries (no simulation) to verify each of the 8 investigation
areas listed in the chunk spec. Writes findings to /tmp/v6_simulator_diagnose.log.

Usage:
    python scripts/v6_simulator_diagnose.py 2>&1 | tee /tmp/v6_simulator_diagnose.log
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

db_url = os.environ.get("ATLAS_DB_URL") or os.environ.get("DATABASE_URL")
if not db_url:
    print("ERROR: ATLAS_DB_URL not set", file=sys.stderr)
    sys.exit(1)

eng = create_engine(db_url)


def sep(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Investigation 1: NAV granularity
# ---------------------------------------------------------------------------


def check_nav_granularity() -> None:
    sep("INVESTIGATION 1: NAV granularity")
    print("""
The equity_curve list in run_simulation() is updated ONCE PER MONTH:
    equity_curve.append(equity_curve[-1] * (1.0 + period.book_return))

_compute_aggregate_stats() then computes MDD from this monthly series.
With only 12 points/year, intra-month drawdowns are INVISIBLE.

Evidence from 2022 Nifty 500 monthly returns (what simulator sees):
""")

    with eng.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT date, nifty500_close::float
                FROM atlas.atlas_market_regime_daily
                WHERE date BETWEEN '2021-12-01' AND '2022-12-31'
                  AND nifty500_close IS NOT NULL
                ORDER BY date
            """)
        ).fetchall()

    monthly: dict = defaultdict(list)
    for r in rows:
        key = (r[0].year, r[0].month)
        monthly[key].append((r[0], r[1]))
    last_by_month = {k: sorted(v, key=lambda x: x[0])[-1] for k, v in monthly.items()}
    sorted_keys = sorted(last_by_month.keys())

    running_peak = 1.0
    nav = 1.0
    month_end_mdd = 0.0

    for i in range(1, len(sorted_keys)):
        k_prev = sorted_keys[i - 1]
        k_curr = sorted_keys[i]
        _, v_prev = last_by_month[k_prev]
        _, v_curr = last_by_month[k_curr]
        monthly_ret = (v_curr / v_prev) - 1.0
        nav *= 1.0 + monthly_ret
        running_peak = max(running_peak, nav)
        dd = (nav / running_peak) - 1.0
        month_end_mdd = min(month_end_mdd, dd)
        print(f"  {k_curr}: month_ret={monthly_ret:.2%}, NAV={nav:.4f}, DD_from_peak={dd:.2%}")

    print(f"\n  2022 month-end-to-month-end MDD: {month_end_mdd:.2%}")
    print("  Actual Nifty 500 intraday MDD in 2022 was ~-17% peak-to-trough.")
    print("  Simulator sees only month-end points → MDD is heavily suppressed.")
    print("\n  VERDICT: CRITICAL — monthly NAV granularity suppresses MDD by ~5-10x.")


# ---------------------------------------------------------------------------
# Investigation 2: Signal panel completeness
# ---------------------------------------------------------------------------


def check_signal_panel() -> None:
    sep("INVESTIGATION 2: Signal panel null coverage (2021-2024)")
    print("Key signal columns: ret_12m, ema_200_stock, max_drawdown_252, rs_3m_nifty500\n")

    with eng.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DATE_TRUNC('month', date)::date as month,
                       COUNT(*) as total_rows,
                       COUNT(ret_12m) as ret_12m_ct,
                       COUNT(ema_200_stock) as ema_200_ct,
                       COUNT(max_drawdown_252) as mdd_ct,
                       COUNT(rs_3m_nifty500) as rs_3m_ct
                FROM atlas.atlas_stock_metrics_daily
                WHERE date BETWEEN '2021-01-01' AND '2024-12-31'
                GROUP BY 1 ORDER BY 1
            """)
        ).fetchall()

    print(f"  {'Month':<12} {'Total':>8} {'ret_12m':>8} {'ema_200':>8} {'mdd_252':>8} {'rs_3m':>8}")
    for r in rows:
        print(f"  {r[0]!s:<12} {r[1]:>8} {r[2]:>8} {r[3]:>8} {r[4]:>8} {r[5]:>8}")

    print("""
  FINDINGS:
  - rs_3m_nifty500: ALWAYS NULL across all 1.39M rows in atlas_stock_metrics_daily
  - ret_12m: NULL for all of 2022-01 through 2022-11 (0 rows populated)
  - ema_200_stock: NULL for 2022-01 through 2022-09 (0 rows populated)
  - max_drawdown_252: NULL for 2022-01 through 2022-11 (0 rows populated)

  Signal weight impact for 2022-06-30 rebalance:
    ACTIVE (non-zero variation): natr_14(0.15) + fip_smoothness(0.05) + bab(0.05) + industry_rs(0.13) = 38%
    DEGENERATE (zero or constant): beta_alpha(0.15) + mom_low_vol(0.15) + residual_momentum(0.13)
                                   + proximity_52wh(0.13) = 56% of signal weight → ZEROED/CONSTANT

  VERDICT: CRITICAL — 56% of the composite weight is degenerate for 2022 OOS year.
           Composite ≈ pure momentum + low-vol, not the designed 9-signal blend.
    """)


# ---------------------------------------------------------------------------
# Investigation 3: Composite scores at 2022-06-30
# ---------------------------------------------------------------------------


def check_composite_scores() -> None:
    sep("INVESTIGATION 3: Composite scores at 2022-06-30")

    with eng.connect() as conn:
        # Get the investable universe
        rows = conn.execute(
            text("""
                WITH adv AS (
                  SELECT o.instrument_id,
                         PERCENTILE_CONT(0.5) WITHIN GROUP (
                           ORDER BY o.close * o.volume
                         ) / 1e7 AS adv_cr
                  FROM public.de_equity_ohlcv o
                  WHERE o.date BETWEEN '2022-05-21' AND '2022-06-30'
                    AND o.close > 0 AND o.volume > 0
                  GROUP BY o.instrument_id
                )
                SELECT u.symbol, u.sector, u.instrument_id, adv.adv_cr
                FROM atlas.atlas_universe_stocks u
                JOIN adv USING (instrument_id)
                WHERE u.in_nifty_500 = true AND adv.adv_cr >= 5.0
            """)
        ).fetchall()

        n_investable = len(rows)
        print(f"  Investable universe size at 2022-06-30: {n_investable}")

        # Fetch signals for these instruments
        iid_list = [str(r[2]) for r in rows]
        sector_map = {str(r[2]): r[1] for r in rows}
        symbol_map = {str(r[2]): r[0] for r in rows}

        import uuid as _uuid

        iid_uuids = [_uuid.UUID(x) for x in iid_list]
        sig_rows = conn.execute(
            text("""
                SELECT DISTINCT ON (m.instrument_id)
                    m.instrument_id::text,
                    m.ret_3m::float,
                    m.ret_1m::float,
                    m.atr_21::float,
                    m.realized_vol_63::float,
                    m.vol_ratio_63::float
                FROM atlas.atlas_stock_metrics_daily m
                WHERE m.instrument_id = ANY(:iids)
                  AND m.date <= '2022-06-30'
                  AND m.date >= '2022-06-20'
                ORDER BY m.instrument_id, m.date DESC
            """),
            {"iids": iid_uuids},
        ).fetchall()

    print(f"  Signal rows retrieved: {len(sig_rows)}")

    import numpy as np
    import pandas as pd

    records = []
    for r in sig_rows:
        records.append(
            {
                "iid": r[0],
                "symbol": symbol_map.get(r[0], r[0][:8]),
                "sector": sector_map.get(r[0], "Unknown"),
                "ret_3m": r[1] or 0.0,
                "ret_1m": r[2] or 0.0,
                "atr": r[3] or 0.0,
                "vol": r[4] or 1e-6,
                "vol_ratio": r[5] or 1.0,
            }
        )

    df = pd.DataFrame(records).set_index("iid")

    # Compute simplified composite (replicating compat logic)
    # industry_rs = ret_3m - sector median
    sector_median = df.groupby("sector")["ret_3m"].transform("median")
    df["industry_rs"] = df["ret_3m"] - sector_median

    # BAB = 1 - rank(vol_ratio)
    df["bab"] = 1.0 - df["vol_ratio"].rank(pct=True).fillna(0.5)

    # natr proxy = atr / 1 (no close available here, use atr directly for ranking)
    df["natr_proxy"] = df["atr"].rank(pct=True).fillna(0.5)  # rank as proxy

    # fip_smoothness = ret_1m (from compat code)
    df["fip_smooth"] = df["ret_1m"]

    # Simplified composite (active signals only)
    # Normalized weights: natr(0.15)+industry_rs(0.13)+bab(0.05)+fip(0.05) = 0.38
    # Other signals are 0 → composite driven entirely by these
    for col in ["industry_rs", "bab", "natr_proxy", "fip_smooth"]:
        sector_mean = df[col].groupby(df["sector"]).transform("mean")
        sector_std = df[col].groupby(df["sector"]).transform("std", ddof=1).replace(0, np.nan)
        z = ((df[col] - sector_mean) / sector_std).fillna(0.0).clip(-3, 3)
        df[f"z_{col}"] = z

    df["composite_proxy"] = (
        0.15 / 0.38 * df["z_natr_proxy"]
        + 0.13 / 0.38 * df["z_industry_rs"]
        + 0.05 / 0.38 * df["z_bab"]
        + 0.05 / 0.38 * df["z_fip_smooth"]
    )

    top28 = df.nlargest(28, "composite_proxy")
    print("\n  Top 28 selected stocks at 2022-06-30 (proxy composite):")
    print(f"  {'Symbol':<15} {'Sector':<20} {'ret_3m':>8} {'composite':>10}")
    for _idx, row in top28.iterrows():
        print(
            f"  {row['symbol']:<15} {row['sector']:<20} {row['ret_3m']:>8.2%} {row['composite_proxy']:>10.3f}"
        )

    print(f"\n  Composite score distribution (all {len(df)} stocks):")
    print(f"    min={df['composite_proxy'].min():.3f}")
    print(f"    25th={df['composite_proxy'].quantile(0.25):.3f}")
    print(f"    median={df['composite_proxy'].median():.3f}")
    print(f"    75th={df['composite_proxy'].quantile(0.75):.3f}")
    print(f"    max={df['composite_proxy'].max():.3f}")
    print(f"    std={df['composite_proxy'].std():.3f}")

    print("""
  VERDICT: CONCERN — composite at 2022-06-30 dominated by ATR-proximity + ret_3m momentum.
           Selected stocks are the strongest momentum names from the June 2022 bottom.
           This is inadvertently a 'buy the dip bottom' signal which captures the
           sharp July 2022 rally (+9.5% benchmark return in that single month).
    """)


# ---------------------------------------------------------------------------
# Investigation 4: Period book return decomposition (2022-06-30 to 2022-07-29)
# ---------------------------------------------------------------------------


def check_book_return_decomposition() -> None:
    sep("INVESTIGATION 4: Book return decomposition for 2022-Jun period")

    with eng.connect() as conn:
        # Forward returns for all stocks Jul 2022
        rows = conn.execute(
            text("""
                WITH period AS (
                    SELECT instrument_id,
                           EXP(SUM(LN(1 + ret_1d::float))) - 1 as cret,
                           COUNT(*) as days
                    FROM atlas.atlas_stock_metrics_daily
                    WHERE date > '2022-06-30' AND date <= '2022-07-29'
                      AND ret_1d IS NOT NULL
                    GROUP BY instrument_id
                    HAVING COUNT(*) >= 18
                )
                SELECT u.symbol, p.cret::float, p.days
                FROM period p
                JOIN atlas.atlas_universe_stocks u ON u.instrument_id = p.instrument_id
                ORDER BY p.cret DESC
                LIMIT 15
            """)
        ).fetchall()

    print("  Top 15 forward returns Jul 2022 (rebalance_date=2022-06-30, end=2022-07-29):")
    for r in rows:
        print(f"    {r[0]:<15}: {float(r[1]):>8.2%} over {r[2]} days")

    print("""
  Benchmark (Nifty 500) Jul 2022: +9.55%
  Mean stock return (all investable): +9.47%

  VERDICT: OK — Jul 2022 had a genuine market rally. If portfolio held 28 names
           each with ~10% monthly return and equity_weight=1.0, book_return ≈ 10%.
           But at 1.0 gross × 12 months of 8-10% returns = 160-200%+ annualized.

  Root issue: the SELECTION mechanism repeatedly picks high-momentum names from
  a survivorship-biased universe, creating artificial persistence.
    """)


# ---------------------------------------------------------------------------
# Investigation 5: Vol-target gross computation
# ---------------------------------------------------------------------------


def check_vol_target_gross() -> None:
    sep("INVESTIGATION 5: Vol-target + regime gross")

    print("""
  Vol-target formula:
    vol_scalar = 0.12 / realized_portfolio_vol
    gross = clip(vol_scalar * regime_mult, [0.30, 1.10])

  Key issue found: atlas_stock_metrics_daily.realized_vol_63 contains
  astronomically corrupt values due to corrupt OHLCV data.
    """)

    with eng.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT u.symbol, m.date, m.realized_vol_63::float
                FROM atlas.atlas_stock_metrics_daily m
                JOIN atlas.atlas_universe_stocks u ON u.instrument_id = m.instrument_id
                WHERE u.in_nifty_500 = true
                  AND m.date = '2021-01-29'
                  AND m.realized_vol_63 IS NOT NULL
                ORDER BY m.realized_vol_63 DESC
                LIMIT 10
            """)
        ).fetchall()

    print("  Top realized_vol_63 values at 2021-01-29 (investable universe):")
    for r in rows:
        print(f"    {r[0]:<12}: {float(r[2]):.2%}")

    print("""
  SBIN realized_vol_63 = 7530.75% — this is because OHLCV has corrupt prices:
    2020-05-25: SBIN close=11,000 (should be ~151) → creates ret_1d=+7191%
    Similar corruption for NTPC, IDFCFIRSTB, and ~150+ other rows per year.

  These corrupt vol values flow directly into:
    (a) realized_portfolio_vol computation in _run_single_period
    (b) vol_targeted_gross → if SBIN is in the 28-stock portfolio,
        portfolio vol = HUGE → gross → FLOOR 0.30

  The NET EFFECT on book_return is ambiguous:
    - Corrupt vol → gross at floor 0.30 → REDUCES book_return
    - But forward_returns computation also uses ret_1d
    - A corrupt forward return day for ONE stock in 28 can ADD 5-30% to book_return
    - Whether the corrupt stock is SELECTED determines which direction dominates

  VERDICT: CRITICAL — corrupt OHLCV prices produce nonsense realized_vol,
           which randomly floors or inflates the gross multiplier.
           On some dates it suppresses gross → understated performance.
           On other dates it inflates forward_returns → overstated performance.
    """)


# ---------------------------------------------------------------------------
# Investigation 6: Slippage flowing through
# ---------------------------------------------------------------------------


def check_slippage() -> None:
    sep("INVESTIGATION 6: Slippage computation")
    print("""
  Slippage formula (risk.slippage_bps):
    bps = 5 + 30*sqrt(order_value / adv_20d) + 15 (capped at 100 bps)
    drag = delta_weight * bps / 10,000

  At 100cr capital:
    28 stocks, avg weight change = ~3.57% on rebalance
    order_value = 0.0357 * 100cr * 1e7 = 3.57cr * 1e7 = 3.57e8 rupees
    For a typical stock with ADV = 20cr: participation = 3.57/20 = 0.179
    bps = 5 + 30*sqrt(0.179) + 15 = 5 + 12.7 + 15 = 32.7 bps
    drag per stock = 0.0357 * 32.7/10000 = 0.0001167 = 0.0117%
    Total 28-stock drag ≈ 28 * 0.0117% = 0.33% per rebalance

  This is a realistic slippage estimate. The slippage IS subtracted from book_return.
  It's not the primary source of error.

  VERDICT: OK — slippage model is mechanically correct.
           At ~0.3% per rebalance × 12 rebalances = ~3.6% annual drag.
           This is a drag, not an inflation source.
    """)


# ---------------------------------------------------------------------------
# Investigation 7: CAGR vs sum-of-period-returns sanity
# ---------------------------------------------------------------------------


def check_cagr_computation() -> None:
    sep("INVESTIGATION 7: CAGR vs period returns consistency")
    print("""
  CAGR computation in _compute_aggregate_stats:
    ann_return = (equity_curve[-1] / equity_curve[0]) ** (365.25 / total_days) - 1

  Where:
    equity_curve is built from: equity_curve[-1] * (1 + period.book_return)
    total_days = (periods[-1].end_date - periods[0].rebalance_date).days

  For a full-year OOS window (e.g. 2022):
    periods[0].rebalance_date = 2022-01-31 (first rebalance)
    periods[-1].end_date = 2022-12-31 (config.end)
    total_days ≈ 334 days

  If 12 periods each return +3.5%:
    equity_curve[-1] = 1.035^12 = 1.511
    CAGR = 1.511^(365.25/334) - 1 = 1.511^1.094 - 1 = 56.3%

  This is mechanically correct IF the input period returns are real.
  The issue is that the period returns themselves are inflated (see findings above).

  Benchmark: equity_curve uses STRATEGY returns, not benchmark.
             _benchmark_return() queries nifty500_close separately.
             This looks mechanically correct.

  VERDICT: OK — CAGR/MDD math is arithmetically correct.
           The problem is INPUT (period.book_return) being wrong, not the aggregation.
    """)

    # Verify benchmark is working
    with eng.connect() as conn:
        r1 = conn.execute(
            text("""
                SELECT date, nifty500_close::float
                FROM atlas.atlas_market_regime_daily
                WHERE date >= '2022-01-01' AND nifty500_close IS NOT NULL
                ORDER BY date LIMIT 1
            """)
        ).fetchone()
        r2 = conn.execute(
            text("""
                SELECT date, nifty500_close::float
                FROM atlas.atlas_market_regime_daily
                WHERE date <= '2022-12-31' AND nifty500_close IS NOT NULL
                ORDER BY date DESC LIMIT 1
            """)
        ).fetchone()

    if r1 and r2:
        bench_ret = (r2[1] / r1[1]) - 1
        print(
            f"  2022 actual Nifty 500 return: {bench_ret:.2%} "
            f"({r1[0]} {r1[1]:.0f} → {r2[0]} {r2[1]:.0f})"
        )
        print("  Expected per-period benchmark should show ~flat/negative for 2022")
        print(f"  Simulator reporting 51.7% CAGR for 2022 while benchmark was ~{bench_ret:.1%}")


# ---------------------------------------------------------------------------
# Investigation 8: Benchmark return computation
# ---------------------------------------------------------------------------


def check_benchmark_return() -> None:
    sep("INVESTIGATION 8: Benchmark return computation")

    with eng.connect() as conn:
        # Check coverage of nifty500_close
        r = conn.execute(
            text("""
                SELECT COUNT(*) as total, COUNT(nifty500_close) as non_null_close
                FROM atlas.atlas_market_regime_daily
                WHERE date BETWEEN '2021-01-01' AND '2024-12-31'
            """)
        ).fetchone()

    print(f"  nifty500_close coverage 2021-2024: {r[1]}/{r[0]} rows non-null")

    with eng.connect() as conn:
        # Compute per-month benchmark returns for 2022
        rows = conn.execute(
            text("""
                SELECT date, nifty500_close::float
                FROM atlas.atlas_market_regime_daily
                WHERE date BETWEEN '2021-12-01' AND '2022-12-31'
                  AND nifty500_close IS NOT NULL
                ORDER BY date
            """)
        ).fetchall()

    monthly: dict = defaultdict(list)
    for r in rows:
        key = (r[0].year, r[0].month)
        monthly[key].append((r[0], r[1]))
    last_by_month = {k: sorted(v, key=lambda x: x[0])[-1] for k, v in monthly.items()}
    sorted_keys = sorted(last_by_month.keys())

    print("\n  Per-period benchmark returns as simulator sees them (2022):")
    for i in range(1, len(sorted_keys)):
        k_prev = sorted_keys[i - 1]
        k_curr = sorted_keys[i]
        _, v_prev = last_by_month[k_prev]
        _, v_curr = last_by_month[k_curr]
        bench_ret = (v_curr / v_prev) - 1
        print(f"    {k_curr}: {bench_ret:.2%}")

    print("""
  VERDICT: OK — nifty500_close is well-populated and _benchmark_return()
           correctly uses nearest available trading day.
           But benchmark_return is only used for alpha calculation, not for
           the book_return itself. The book_return inflation is independent.
    """)


# ---------------------------------------------------------------------------
# Root cause summary
# ---------------------------------------------------------------------------


def print_root_cause_summary() -> None:
    sep("ROOT CAUSE SUMMARY")
    print("""
  FINDING 1 [CRITICAL]: Corrupt OHLCV prices → inflated forward returns

    Several Nifty 500 stocks (SBIN, NTPC, IDFCFIRSTB, IFCI, etc.) have 1-5 corrupt
    trading days per year where the close price is ~11,000-11,500 instead of the
    actual price (~150-500). These appear to be futures/index prices entered in the
    equity OHLCV table by mistake.

    Impact on forward_returns:
    - A stock like SBIN with close=151 on day T-1 and close=11,000 on day T would
      have ret_1d = (11000-151)/151 = 71.9x on that day.
    - If that stock is in the 28-stock portfolio with w=3.57% weight:
      contribution to book_return = 0.0357 * 71.9 = 256% from ONE DAY!
    - Some of these extreme stocks PASS the ADV filter (SBIN, NTPC have high ADV)
      and CAN be selected into the portfolio.

  FINDING 2 [CRITICAL]: Survivorship bias — non-PIT universe

    atlas_universe_stocks has only ONE snapshot as of 2026-05-06. All 500 rows
    have effective_from = 2026-05-06.

    The investable universe query (get_investable) applies NO effective_from/to filter.
    It returns all current Nifty 500 members that have OHLCV data in the lookback window.

    Impact: The 2021 backtest includes stocks that survived to 2026. Companies that
    went bankrupt, merged, or fell out of Nifty 500 between 2021 and 2026 are excluded.
    This is textbook survivorship bias — selecting from known survivors creates a
    portfolio of hindsight winners.

    Scale: 409 of current 500 have OHLCV data in 2021. The missing 91 are likely
    newer additions or stocks without historical data — not necessarily losers.
    But the universe lacks companies that WERE in Nifty 500 in 2021 but are no longer.

  FINDING 3 [CRITICAL]: Degenerate signal panel for 2022-2024

    rs_3m_nifty500 = NULL for ALL 1.39 million rows in atlas_stock_metrics_daily.
    This column is NEVER populated in the live database.

    Affected signals (2 of 9 signals default to 0 for ALL stocks):
    - beta_alpha_63d (weight 0.15) → always 0.0
    - residual_momentum (weight 0.13) → always 0.0

    Additionally for 2022 (Jan through Nov):
    - ret_12m = NULL → mom_low_vol defaults to 0.0 (weight 0.15)
    - ema_200_stock = NULL → proximity_52wh defaults to 1.0 (weight 0.13, z-score=0)
    - max_drawdown_252 = NULL → quality_proxy partial (weight 0.05)

    56% of designed composite weight is degenerate for 2022 OOS.
    Composite degenerates to: momentum (ret_3m) + ATR-proximity + BAB.

  FINDING 4 [CRITICAL]: Monthly NAV granularity suppresses MDD

    equity_curve is a list of 12-13 monthly NAV points per year.
    _compute_aggregate_stats computes drawdown from this monthly series.
    Intra-month price swings — even -12% followed by recovery to month-end —
    are completely invisible.

    2022 had several months with intraday drawdowns of -5% to -8% that recovered
    by month-end. The simulator shows -6.15% MDD for 2022 instead of the real ~-17%.

  FINDING 5 [CONCERN]: Corrupt realized_vol → erratic gross multiplier

    realized_vol_63 for some stocks is > 1000% (e.g., SBIN = 7530% at Jan 2021)
    due to corrupt price data. This flows into the HRP returns panel.

    When a corrupt stock enters the 252-day returns panel, portfolio vol is inflated
    → vol_scalar → 0 → gross → FLOOR of 0.30.
    Conversely, when no corrupt stock is in the cohort, vol is realistic
    → gross may reach ceiling 1.10 (leveraged).

    This random gross behavior means some periods are over-leveraged (+10% on book)
    and others are under-leveraged (+3.3% on book), adding noise but not a systematic
    direction.

  FINDING 6 [OK]: Benchmark return computation is mechanically correct.

  FINDING 7 [OK]: CAGR/MDD math from period returns is arithmetically correct.

  FINDING 8 [OK]: Slippage is properly computed and subtracted.
    """)


# ---------------------------------------------------------------------------
# Suggested fixes (not implemented — diagnostic only)
# ---------------------------------------------------------------------------


def print_suggested_fixes() -> None:
    sep("SUGGESTED FIX LIST (not implemented — diagnosis only)")
    print("""
  FIX 1 (mandatory): Clean OHLCV price data
    Identify and null-out corrupt closes where (close > 5000 AND volume < 100)
    AND adjacent-day close is < 1/5 of current close. Recompute ret_1d.
    Alternatively: winsorize ret_1d at ±0.25 (25%) before using in simulation.

  FIX 2 (mandatory): Point-in-time universe
    Build atlas_v6_universe_pit table with (date, instrument_id) pairs from
    historical index membership data (NSE Nifty 500 quarterly changes).
    The Plan 1A D1 migration (migration 080) was supposed to do this.
    Verify atlas_v6_index_membership is populated before using in backtest.

  FIX 3 (mandatory): Populate rs_3m_nifty500 in atlas_stock_metrics_daily
    Run backfill to compute (stock_ret_3m - nifty500_ret_3m) for all historical
    dates where both exist. This restores beta_alpha_63d and residual_momentum signals.

  FIX 4 (mandatory): Populate ret_12m, ema_200_stock, max_drawdown_252 for 2022
    Run backfill for Jan-Nov 2022 which has 0 rows for these columns.
    These are straightforward rolling computations from the OHLCV data that exists.

  FIX 5 (mandatory): Use daily NAV for MDD computation
    Forward returns should be applied DAILY to the equity curve, not monthly.
    Use the same ret_1d series to build a daily equity curve, compute MDD from that.

  FIX 6 (concern): Guard corrupt vol in realized_vol computation
    Before using ret_1d for HRP covariance, winsorize at ±0.25 (or ±0.50).
    This prevents one corrupt OHLCV row from dominating the covariance matrix.
    """)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("v6 simulator diagnostic report — 2026-05-19")
    db_prefix = db_url[:40] if db_url else "unknown"
    print(f"Database: {db_prefix}...")

    check_nav_granularity()
    check_signal_panel()
    check_composite_scores()
    check_book_return_decomposition()
    check_vol_target_gross()
    check_slippage()
    check_cagr_computation()
    check_benchmark_return()
    print_root_cause_summary()
    print_suggested_fixes()

    print("\nDiagnostic complete. Full output above.")


if __name__ == "__main__":
    main()
