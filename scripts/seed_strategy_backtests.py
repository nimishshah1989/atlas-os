#!/usr/bin/env python3
# allow-large: one-shot seed script; each strategy branch is self-contained, splitting would lose cohesion
"""Bulk-seed backtest results for all 15 systematic strategies.

Signal approach: RS STATE TRANSITIONS (not nightly trigger booleans).
The historical decisions tables have almost zero entry triggers (designed
for nightly paper-trading deltas). For a multi-year backtest, the correct
entry signal is the day an instrument ENTERS the allowed RS state
(e.g., transitions from Consolidating → Leader), and exit is the day
it LEAVES that state (or hard exit triggers fire).

Runs on EC2 where vectorbt is installed. Sequential per strategy.
Results written to atlas.strategy_backtest_results.

Usage:
    python scripts/seed_strategy_backtests.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
    python scripts/seed_strategy_backtests.py --strategy stocks_momentum_aggressive

Defaults:
    --start 2022-01-01
    --end   2025-12-31

Re-running is safe: inserts a new row each time.
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from atlas.simulation.backtest.engine import BacktestResult, run_backtest
from atlas.simulation.backtest.report import write_backtest_result
from atlas.simulation.core.signal_adapter import SignalMatrix
from atlas.simulation.strategies.loader import StrategyConfig, load_all_configs

log = structlog.get_logger()

# Mirrors paper_trader._STATE_FILTER_MAP
_STATE_FILTER_MAP: dict[str, set[str] | None] = {
    "leader": {"Leader"},
    "strong": {"Leader", "Strong"},
    "emerging": {"Leader", "Strong", "Emerging"},
    "investable": None,
}


def _resolve_allowed_states(state_filter: list[str]) -> set[str] | None:
    allowed: set[str] = set()
    for sf in state_filter:
        mapped = _STATE_FILTER_MAP.get(sf.lower())
        if mapped is None:
            return None
        allowed |= mapped
    return allowed or None


# ---------------------------------------------------------------------------
# Signal matrix builders — RS state transition approach
# ---------------------------------------------------------------------------


def _build_stock_matrix(
    engine: Engine,
    start_date: date,
    end_date: date,
    allowed_states: set[str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build stock signal matrix using RS state transitions.

    Entry = day instrument enters allowed_states.
    Exit  = day it leaves allowed_states, or hard exit triggers fire.
    """
    if allowed_states is None:
        log.warning(
            "seed_bt_stocks_investable_skip",
            reason="is_investable not backfilled — returning empty matrix",
        )
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    states_list = list(allowed_states)

    with open_compute_session(engine) as conn:
        id_rows = conn.execute(
            text("""
                SELECT DISTINCT instrument_id::text
                FROM atlas.atlas_stock_states_daily
                WHERE date BETWEEN :start AND :end
                  AND rs_state = ANY(:states)
            """),
            {"states": states_list, "start": start_date, "end": end_date},
        ).fetchall()

    instrument_ids = [r[0] for r in id_rows]
    if not instrument_ids:
        log.warning("seed_bt_stocks_no_instruments", states=states_list)
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    log.info("seed_bt_stocks_instruments", count=len(instrument_ids), states=states_list)

    sql = text("""
        WITH lagged AS (
          SELECT
            s.date,
            s.instrument_id::text                        AS instrument_id,
            (s.rs_state = ANY(:states))                  AS in_state,
            LAG(s.rs_state = ANY(:states))
              OVER (PARTITION BY s.instrument_id ORDER BY s.date)
                                                         AS prev_in_state
          FROM atlas.atlas_stock_states_daily s
          WHERE s.date BETWEEN :start AND :end
            AND s.instrument_id::text = ANY(:ids)
        )
        SELECT
          l.date,
          l.instrument_id,
          p.close_adj                                    AS price,
          (l.in_state AND NOT COALESCE(l.prev_in_state, FALSE))
                                                         AS entry_signal,
          (
            (NOT l.in_state AND COALESCE(l.prev_in_state, FALSE))
            OR COALESCE(d.exit_rs_deteriorate,     FALSE)
            OR COALESCE(d.exit_market_riskoff,     FALSE)
            OR COALESCE(d.exit_momentum_collapse,  FALSE)
            OR COALESCE(d.exit_stop_loss,          FALSE)
          )                                              AS exit_signal
        FROM lagged l
        JOIN de_equity_ohlcv p
          ON p.instrument_id::text = l.instrument_id AND p.date = l.date
        LEFT JOIN atlas.atlas_stock_decisions_daily d
          ON d.instrument_id::text = l.instrument_id AND d.date = l.date
        WHERE p.close_adj IS NOT NULL
        ORDER BY l.date, l.instrument_id
    """)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            sql,
            conn,
            params={
                "states": states_list,
                "start": start_date,
                "end": end_date,
                "ids": instrument_ids,
            },
        )

    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    price_p = df.pivot(index="date", columns="instrument_id", values="price").sort_index()
    entry_p = (
        df.pivot(index="date", columns="instrument_id", values="entry_signal")
        .sort_index()
        .fillna(False)
    )
    exit_p = (
        df.pivot(index="date", columns="instrument_id", values="exit_signal")
        .sort_index()
        .fillna(False)
    )

    price_p = price_p.ffill(limit=5)
    price_p = price_p.dropna(axis=1)
    if price_p.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    keep = price_p.columns
    entry_p = entry_p.reindex(columns=keep).fillna(False)
    exit_p = exit_p.reindex(columns=keep).fillna(False)
    return price_p, entry_p, exit_p


def _build_etf_matrix(
    engine: Engine,
    start_date: date,
    end_date: date,
    allowed_states: set[str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build ETF signal matrix using RS state transitions.

    ETFs can only be in {Average, Strong, Weak, ILLIQUID, INSUFFICIENT_HISTORY}.
    'Leader' in the state filter is treated as 'Strong' for ETFs (no Leader state exists).
    """
    if allowed_states is None:
        log.warning(
            "seed_bt_etfs_investable_skip",
            reason="investable not backfilled for ETFs — returning empty matrix",
        )
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Map leader → strong for ETFs (no Leader state in atlas_etf_states_daily)
    etf_states = set()
    for st in allowed_states:
        etf_states.add("Strong" if st == "Leader" else st)
    states_list = list(etf_states)

    with open_compute_session(engine) as conn:
        id_rows = conn.execute(
            text("""
                SELECT DISTINCT ticker
                FROM atlas.atlas_etf_states_daily
                WHERE date BETWEEN :start AND :end
                  AND rs_state = ANY(:states)
            """),
            {"states": states_list, "start": start_date, "end": end_date},
        ).fetchall()

    tickers = [r[0] for r in id_rows]
    if not tickers:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    sql = text("""
        WITH lagged AS (
          SELECT
            s.date,
            s.ticker                                     AS instrument_id,
            (s.rs_state = ANY(:states))                  AS in_state,
            LAG(s.rs_state = ANY(:states))
              OVER (PARTITION BY s.ticker ORDER BY s.date)
                                                         AS prev_in_state
          FROM atlas.atlas_etf_states_daily s
          WHERE s.date BETWEEN :start AND :end
            AND s.ticker = ANY(:tickers)
        )
        SELECT
          l.date,
          l.instrument_id,
          p.close                                        AS price,
          (l.in_state AND NOT COALESCE(l.prev_in_state, FALSE))
                                                         AS entry_signal,
          (
            (NOT l.in_state AND COALESCE(l.prev_in_state, FALSE))
            OR COALESCE(d.exit_rs_deteriorate,     FALSE)
            OR COALESCE(d.exit_market_riskoff,     FALSE)
          )                                              AS exit_signal
        FROM lagged l
        JOIN de_etf_ohlcv p
          ON p.ticker = l.instrument_id AND p.date = l.date
        LEFT JOIN atlas.atlas_etf_decisions_daily d
          ON d.ticker = l.instrument_id AND d.date = l.date
        WHERE p.close IS NOT NULL
        ORDER BY l.date, l.instrument_id
    """)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            sql,
            conn,
            params={
                "states": states_list,
                "start": start_date,
                "end": end_date,
                "tickers": tickers,
            },
        )

    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    price_p = df.pivot(index="date", columns="instrument_id", values="price").sort_index()
    entry_p = (
        df.pivot(index="date", columns="instrument_id", values="entry_signal")
        .sort_index()
        .fillna(False)
    )
    exit_p = (
        df.pivot(index="date", columns="instrument_id", values="exit_signal")
        .sort_index()
        .fillna(False)
    )

    price_p = price_p.ffill(limit=5)
    price_p = price_p.dropna(axis=1)
    if price_p.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    keep = price_p.columns
    entry_p = entry_p.reindex(columns=keep).fillna(False)
    exit_p = exit_p.reindex(columns=keep).fillna(False)
    return price_p, entry_p, exit_p


def _build_fund_matrix(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build fund signal matrix using atlas_fund_states_daily.nav_state transitions.

    Entry = fund transitions INTO 'Leader NAV' state.
    Exit  = fund transitions OUT OF 'Leader NAV' state OR hard exit triggers.

    The is_investable / entry_trigger columns in atlas_fund_decisions_daily are
    unpopulated (pipeline gap). nav_state from atlas_fund_states_daily is the
    correct investability signal for funds.
    """
    sql = text("""
        WITH lagged AS (
          SELECT
            s.date,
            s.mstar_id                                           AS instrument_id,
            (s.nav_state = 'Leader NAV')                        AS in_state,
            LAG(s.nav_state = 'Leader NAV')
              OVER (PARTITION BY s.mstar_id ORDER BY s.date)    AS prev_in_state
          FROM atlas.atlas_fund_states_daily s
          WHERE s.date BETWEEN :start AND :end
        )
        SELECT
          l.date,
          l.instrument_id,
          n.nav                                                  AS price,
          (l.in_state AND NOT COALESCE(l.prev_in_state, FALSE)) AS entry_signal,
          (
            (NOT l.in_state AND COALESCE(l.prev_in_state, FALSE))
            OR COALESCE(d.exit_market_riskoff,          FALSE)
            OR COALESCE(d.exit_composition_misaligned,  FALSE)
            OR COALESCE(d.exit_holdings_weak,           FALSE)
            OR COALESCE(d.exit_nav_deteriorate,         FALSE)
          )                                                      AS exit_signal
        FROM lagged l
        JOIN de_mf_nav_daily n
          ON n.mstar_id = l.instrument_id AND n.nav_date = l.date
        LEFT JOIN atlas.atlas_fund_decisions_daily d
          ON d.mstar_id = l.instrument_id AND d.date = l.date
        WHERE n.nav IS NOT NULL
        ORDER BY l.date, l.instrument_id
    """)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(sql, conn, params={"start": start_date, "end": end_date})

    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    price_p = df.pivot(index="date", columns="instrument_id", values="price").sort_index()
    entry_p = (
        df.pivot(index="date", columns="instrument_id", values="entry_signal")
        .sort_index()
        .fillna(False)
    )
    exit_p = (
        df.pivot(index="date", columns="instrument_id", values="exit_signal")
        .sort_index()
        .fillna(False)
    )

    price_p = price_p.ffill(limit=5)
    # Drop funds with any remaining NaN prices — gaps break vectorbt return calcs
    price_p = price_p.dropna(axis=1)
    if price_p.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    keep_cols = price_p.columns
    entry_p = entry_p.reindex(columns=keep_cols).fillna(False)
    exit_p = exit_p.reindex(columns=keep_cols).fillna(False)
    return price_p, entry_p, exit_p


def _combine_pivots(
    stock_pivots: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    etf_pivots: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Merge stock + ETF pivots into a single signal matrix."""
    s_price, s_entry, s_exit = stock_pivots
    e_price, e_entry, e_exit = etf_pivots

    if s_price.empty and e_price.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if s_price.empty:
        return e_price, e_entry, e_exit
    if e_price.empty:
        return s_price, s_entry, s_exit

    price_p = pd.concat([s_price, e_price], axis=1).sort_index()
    entry_p = pd.concat([s_entry, e_entry], axis=1).sort_index().fillna(False)
    exit_p = pd.concat([s_exit, e_exit], axis=1).sort_index().fillna(False)

    price_p = price_p.ffill(limit=5).dropna(how="all")
    common_idx = price_p.index
    entry_p = entry_p.reindex(common_idx).fillna(False)
    exit_p = exit_p.reindex(common_idx).fillna(False)

    return price_p, entry_p, exit_p


# ---------------------------------------------------------------------------
# Regime helpers
# ---------------------------------------------------------------------------

# Risk-off = deployment_multiplier = 0 (Risk-Off + DISLOCATION_SUSPENDED states)
_RISK_OFF_MULTIPLIER = 0


def _risk_off_dates_set(engine: Engine, start_date: date, end_date: date) -> set[date]:
    """Return dates where market is fully risk-off (deployment_multiplier = 0)."""
    sql = text("""
        SELECT date FROM atlas.atlas_market_regime_daily
        WHERE date BETWEEN :start AND :end
          AND deployment_multiplier = :mult
        ORDER BY date
    """)
    with engine.connect() as conn:
        rows = conn.execute(
            sql, {"start": start_date, "end": end_date, "mult": _RISK_OFF_MULTIPLIER}
        ).fetchall()
    return {r[0] for r in rows}


def _apply_regime_filter(
    entry_p: pd.DataFrame,
    exit_p: pd.DataFrame,
    risk_off_dates: set[date],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """On risk-off days: block all new entries and force-exit all open positions."""
    if not risk_off_dates:
        return entry_p, exit_p
    risk_off_idx = [ts for ts in entry_p.index if pd.Timestamp(ts).date() in risk_off_dates]
    if not risk_off_idx:
        return entry_p, exit_p
    entry_p = entry_p.copy()
    exit_p = exit_p.copy()
    entry_p.loc[risk_off_idx] = False
    exit_p.loc[risk_off_idx] = True
    return entry_p, exit_p


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------


def _nifty500_cagr(engine: Engine, start_date: date, end_date: date) -> float | None:
    """Return Nifty 500 annualized return (CAGR) for the given date range.

    Uses de_index_prices.close for index_code = 'NIFTY 500'.
    Picks the nearest available date on or after start_date and on or before end_date.
    Returns None if insufficient data.
    """
    sql = text("""
        SELECT
          (SELECT close FROM de_index_prices
           WHERE index_code = 'NIFTY 500' AND date >= :start ORDER BY date ASC LIMIT 1)
            AS start_close,
          (SELECT close FROM de_index_prices
           WHERE index_code = 'NIFTY 500' AND date <= :end   ORDER BY date DESC LIMIT 1)
            AS end_close,
          (SELECT date FROM de_index_prices
           WHERE index_code = 'NIFTY 500' AND date >= :start ORDER BY date ASC LIMIT 1)
            AS actual_start,
          (SELECT date FROM de_index_prices
           WHERE index_code = 'NIFTY 500' AND date <= :end   ORDER BY date DESC LIMIT 1)
            AS actual_end
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"start": start_date, "end": end_date}).fetchone()

    if row is None or row[0] is None or row[1] is None:
        return None

    start_close, end_close, actual_start, actual_end = (
        float(row[0]),
        float(row[1]),
        row[2],
        row[3],
    )
    days = (actual_end - actual_start).days
    if days <= 0 or start_close <= 0:
        return None

    return (end_close / start_close) ** (365.25 / days) - 1


def _write_alpha(engine: Engine, backtest_id: str, alpha: float) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE atlas.strategy_backtest_results
                SET alpha_vs_nifty500 = :alpha
                WHERE id = CAST(:bid AS uuid)
            """),
            {"alpha": alpha, "bid": backtest_id},
        )


# ---------------------------------------------------------------------------
# Per-strategy orchestration
# ---------------------------------------------------------------------------


def _get_strategy_id(engine: Engine, name: str) -> str | None:
    with open_compute_session(engine) as conn:
        row = conn.execute(
            text("SELECT id::text FROM atlas.strategy_configs WHERE name = :name LIMIT 1"),
            {"name": name},
        ).fetchone()
    return str(row[0]) if row else None


def run_strategy_backtest(
    engine: Engine,
    cfg: StrategyConfig,
    strategy_id: str,
    start_date: date,
    end_date: date,
) -> str | None:
    """Run one strategy backtest. Returns backtest_id or None on failure/skip."""
    t0 = time.time()
    allowed_states = _resolve_allowed_states(cfg.state_filter)
    tier = cfg.tier

    log.info(
        "seed_bt_start",
        strategy=cfg.name,
        tier=tier,
        allowed_states=list(allowed_states) if allowed_states else "any",
    )

    try:
        if tier == "stocks_only":
            price_p, entry_p, exit_p = _build_stock_matrix(
                engine, start_date, end_date, allowed_states
            )

        elif tier == "fund_only":
            price_p, entry_p, exit_p = _build_fund_matrix(engine, start_date, end_date)

        else:  # blend
            stock_pivots = _build_stock_matrix(engine, start_date, end_date, allowed_states)
            etf_pivots = _build_etf_matrix(engine, start_date, end_date, allowed_states)
            price_p, entry_p, exit_p = _combine_pivots(stock_pivots, etf_pivots)

        if price_p.empty:
            print(f"  ⚠  {cfg.name} — empty signal matrix; skipping")
            log.warning("seed_bt_empty_matrix", strategy=cfg.name)
            return None

        # Apply regime filter: on risk-off days block entries and force exits
        if cfg.regime_stance == "pause_risk_off":
            risk_off = _risk_off_dates_set(engine, start_date, end_date)
            entry_p, exit_p = _apply_regime_filter(entry_p, exit_p, risk_off)
            log.info(
                "seed_bt_regime_filter",
                strategy=cfg.name,
                risk_off_days=len(risk_off),
            )

        instruments = list(price_p.columns)
        dates = pd.DatetimeIndex(price_p.index)

        signal_matrix = SignalMatrix(
            prices=price_p.values.astype(np.float64),
            entries=entry_p.values.astype(bool),
            exits=exit_p.values.astype(bool),
            dates=dates,
            instruments=instruments,
        )

        n_entries = int(signal_matrix.entries.sum())
        log.info(
            "seed_bt_matrix_ready",
            strategy=cfg.name,
            instruments=len(instruments),
            dates=len(dates),
            entry_signals=n_entries,
        )

        if n_entries == 0:
            print(f"  ⚠  {cfg.name} — zero entry signals after state filtering; skipping")
            log.warning(
                "seed_bt_zero_entries", strategy=cfg.name, states=list(allowed_states or [])
            )
            return None

        result: BacktestResult = run_backtest(
            signal_matrix,
            init_cash=10_000_000.0,
            max_positions=cfg.max_positions,
        )

        backtest_id = write_backtest_result(
            engine=engine,
            result=result,
            backtest_type="full",
            strategy_id=UUID(strategy_id),
        )

        # Compute and store alpha vs Nifty 500
        n500_cagr = _nifty500_cagr(engine, start_date, end_date)
        alpha_str = "—"
        if n500_cagr is not None and result.total_return is not None and result.total_return > -1:
            days = (end_date - start_date).days
            strat_cagr = (1 + result.total_return) ** (365.25 / days) - 1
            alpha = strat_cagr - n500_cagr
            _write_alpha(engine, backtest_id, alpha)
            alpha_str = f"{alpha:+.3f}"

        elapsed = time.time() - t0
        sharpe_str = f"{result.sharpe_ratio:.3f}" if result.sharpe_ratio is not None else "None"
        ret_str = f"{result.total_return:.3f}" if result.total_return is not None else "None"
        print(
            f"  ✓ {cfg.name:45s}  "
            f"sharpe={sharpe_str:>7}  ret={ret_str:>7}  alpha={alpha_str:>8}  "
            f"instruments={len(instruments):>4}  entries={n_entries:>5}  {elapsed:.1f}s"
        )
        log.info(
            "seed_bt_done",
            strategy=cfg.name,
            backtest_id=backtest_id,
            sharpe=result.sharpe_ratio,
            elapsed=elapsed,
        )

        del signal_matrix
        gc.collect()
        return backtest_id

    except Exception:
        log.exception("seed_bt_failed", strategy=cfg.name)
        print(f"  ✗ {cfg.name} — FAILED (see log above)", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed historical backtest results for all 15 systematic strategies"
    )
    parser.add_argument("--start", default="2022-01-01", metavar="YYYY-MM-DD")
    parser.add_argument("--end", default="2025-12-31", metavar="YYYY-MM-DD")
    parser.add_argument(
        "--strategy", default=None, help="Single strategy name to run (default: all 15)"
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    print("\nAtlas Strategy Backtest Seed  (RS state-transition signals)")
    print(f"  Date range : {start_date} → {end_date}")
    print(f"  Started    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    engine = get_engine()
    configs = load_all_configs()

    if args.strategy:
        configs = [c for c in configs if c.name == args.strategy]
        if not configs:
            print(f"ERROR: strategy '{args.strategy}' not found", file=sys.stderr)
            sys.exit(1)

    total = len(configs)
    succeeded = 0
    failed = 0

    for i, cfg in enumerate(configs, 1):
        print(f"[{i:2d}/{total}] {cfg.name} ({cfg.tier})")
        strategy_id = _get_strategy_id(engine, cfg.name)
        if strategy_id is None:
            print("  ✗ Not in atlas.strategy_configs — run populate_strategy_configs() first")
            failed += 1
            print()
            continue

        bt_id = run_strategy_backtest(engine, cfg, strategy_id, start_date, end_date)
        if bt_id:
            succeeded += 1
        else:
            failed += 1
        print()

    print("─" * 80)
    print(f"Done: {succeeded} succeeded, {failed} failed")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
