"""Strategy Lab backtest validation — the goal-post "proof" pipeline.

Runs each top-N leaderboard genome over the full 12-year history with
yearly walk-forward windows. Persists per-year results to
atlas.atlas_strategy_validation. The Proof tab on /strategies/lab reads
from this table to show "strategy return vs Nifty 500, year by year".

Re-runnable: ON CONFLICT (genome_id, year) DO UPDATE. Heavy compute —
~30 min on .214 single-core for 3 genomes × 12 yearly windows. Intended
to run weekly (not nightly), after a fresh leaderboard refresh.

Usage:
  python scripts/strategy_lab_validation.py [--top-n 3]
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from atlas.trading.config import PortfolioConfig
from atlas.trading.genome import Genome
from atlas.trading.simulator import simulate_genome

log = structlog.get_logger()

_DEFAULT_TOP_N = 3
_HISTORY_YEARS = 12


def _load_top_genomes(conn: Connection, top_n: int) -> list[dict[str, Any]]:
    rows = (
        conn.execute(
            text(
                """
                SELECT l.genome_id::text, l.rank, l.strategy_name, g.genome_json
                FROM atlas.atlas_strategy_leaderboard l
                JOIN atlas.atlas_strategy_genomes g ON g.id = l.genome_id
                ORDER BY l.rank
                LIMIT :n
                """
            ),
            {"n": top_n},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def _load_full_history(
    conn: Connection, start_date: date, end_date: date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics = pd.DataFrame(
        conn.execute(
            text(
                """
                SELECT
                    m.instrument_id, m.date, p.close_adj AS close,
                    m.rs_pctile_1w, m.rs_pctile_1m, m.rs_pctile_3m,
                    m.vol_ratio_63, m.ema_20_ratio
                FROM atlas.atlas_stock_metrics_daily m
                JOIN public.de_equity_ohlcv p
                  ON p.instrument_id = m.instrument_id
                 AND p.date = m.date
                WHERE m.date BETWEEN :start AND :end
                  AND p.close_adj IS NOT NULL
                ORDER BY m.date, m.instrument_id
                """
            ),
            {"start": start_date, "end": end_date},
        )
        .mappings()
        .all()
    )
    regime = pd.DataFrame(
        conn.execute(
            text(
                """
                SELECT date, pct_above_ema_50, india_vix, nifty500_close
                FROM atlas.atlas_market_regime_daily
                WHERE date BETWEEN :start AND :end
                ORDER BY date
                """
            ),
            {"start": start_date, "end": end_date},
        )
        .mappings()
        .all()
    )
    return metrics, regime


def _yearly_window(year: int) -> tuple[date, date, date, date]:
    """Build a walk-forward window for one calendar year.

    For simplicity each year's window has a tiny training prefix (Dec 31 of
    previous year) so simulate_genome treats it as a single OOS window. The
    real backtest is the test_start → test_end (Jan 1 → Dec 31).
    """
    test_start = date(year, 1, 1)
    test_end = date(year, 12, 31)
    train_end = test_start - timedelta(days=1)
    train_start = train_end - timedelta(days=1)
    return (train_start, train_end, test_start, test_end)


def _benchmark_year_stats(regime_df: pd.DataFrame, year: int) -> tuple[float, float]:
    """Compute Nifty 500 return + max drawdown for one calendar year."""
    if regime_df.empty or "nifty500_close" not in regime_df.columns:
        return 0.0, 0.0
    year_df = regime_df[
        (regime_df["date"] >= date(year, 1, 1)) & (regime_df["date"] <= date(year, 12, 31))
    ].copy()
    if year_df.empty:
        return 0.0, 0.0
    # Keep as pandas Series for ffill, convert to list only at the end.
    closes_series = pd.Series(year_df["nifty500_close"].tolist(), dtype=float).ffill()
    closes = [c for c in closes_series.tolist() if c == c and c > 0]  # drop NaN
    if len(closes) < 2:
        return 0.0, 0.0
    yr_return = float(closes[-1] / closes[0] - 1.0)
    # Max drawdown from running peak (return-space, positive number = worst loss)
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        peak = max(peak, c)
        dd = (peak - c) / peak
        if dd > max_dd:
            max_dd = dd
    return yr_return, max_dd


def _write_validation_row(
    conn: Connection,
    genome_id: str,
    year: int,
    sim: Any,
    benchmark_return: float,
    benchmark_max_dd: float,
) -> None:
    strategy_return = float(sim.alpha_oos + benchmark_return)  # invert: alpha = strat − bench
    alpha = float(sim.alpha_oos)
    conn.execute(
        text(
            """
            INSERT INTO atlas.atlas_strategy_validation
                (genome_id, year, strategy_return, benchmark_return, alpha,
                 max_drawdown, benchmark_max_drawdown, sortino, n_trades,
                 avg_positions_held)
            VALUES
                (CAST(:gid AS uuid), :year, :s_ret, :b_ret, :alpha,
                 :max_dd, :b_dd, :sortino, :trades, :avg_pos)
            ON CONFLICT (genome_id, year) DO UPDATE
                SET strategy_return = EXCLUDED.strategy_return,
                    benchmark_return = EXCLUDED.benchmark_return,
                    alpha = EXCLUDED.alpha,
                    max_drawdown = EXCLUDED.max_drawdown,
                    benchmark_max_drawdown = EXCLUDED.benchmark_max_drawdown,
                    sortino = EXCLUDED.sortino,
                    n_trades = EXCLUDED.n_trades,
                    avg_positions_held = EXCLUDED.avg_positions_held,
                    run_at = now()
            """
        ),
        {
            "gid": genome_id,
            "year": year,
            "s_ret": Decimal(str(strategy_return)),
            "b_ret": Decimal(str(benchmark_return)),
            "alpha": Decimal(str(alpha)),
            "max_dd": Decimal(str(sim.max_drawdown)),
            "b_dd": Decimal(str(benchmark_max_dd)),
            "sortino": Decimal(str(sim.sortino_oos)),
            "trades": int(sim.total_trades),
            "avg_pos": Decimal(str(sim.avg_positions_held)),
        },
    )


def run(top_n: int) -> dict[str, Any]:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise RuntimeError("ATLAS_DB_URL not set")
    engine = create_engine(db_url)
    today = date.today()
    start_year = today.year - _HISTORY_YEARS
    summary: dict[str, Any] = {"top_n": top_n, "genomes": [], "rows_written": 0}

    with engine.connect() as conn:
        genomes = _load_top_genomes(conn, top_n)
        if not genomes:
            summary["status"] = "aborted_no_genomes"
            return summary

        # Load all 12 years once — simulate_genome filters by walk-forward windows.
        metrics_df, regime_df = _load_full_history(conn, date(start_year, 1, 1), today)
        if metrics_df.empty:
            summary["status"] = "aborted_no_metrics"
            return summary

        config = PortfolioConfig()
        rows_written = 0

        for row in genomes:
            gid = row["genome_id"]
            genome_json = row["genome_json"]
            if isinstance(genome_json, str):
                genome_json = json.loads(genome_json)
            genome = Genome.from_dict(genome_json)
            per_year: list[dict[str, Any]] = []

            for year in range(start_year, today.year + 1):
                window = _yearly_window(year)
                # Skip future years that don't have full data.
                if window[3] > today:
                    window = (window[0], window[1], window[2], today)
                if window[3] <= window[2]:
                    continue
                sim = simulate_genome(genome, metrics_df, regime_df, config, [window])
                b_ret, b_dd = _benchmark_year_stats(regime_df, year)
                _write_validation_row(conn, gid, year, sim, b_ret, b_dd)
                rows_written += 1
                per_year.append(
                    {
                        "year": year,
                        "alpha": float(sim.alpha_oos),
                        "strategy_return": float(sim.alpha_oos + b_ret),
                        "benchmark_return": float(b_ret),
                        "max_drawdown": float(sim.max_drawdown),
                    }
                )
                log.info(
                    "validation_year_done", genome_id=gid, year=year, alpha=float(sim.alpha_oos)
                )

            summary["genomes"].append(
                {
                    "genome_id": gid,
                    "rank": int(row["rank"]),
                    "strategy_name": row["strategy_name"],
                    "years": per_year,
                }
            )
        conn.commit()

    summary["rows_written"] = rows_written
    summary["status"] = "ok"
    log.info("strategy_lab_validation_done", rows=rows_written, n_genomes=len(genomes))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strategy Lab backtest validation")
    parser.add_argument("--top-n", type=int, default=_DEFAULT_TOP_N)
    args = parser.parse_args()
    result = run(top_n=args.top_n)
    print(json.dumps(result, indent=2))
