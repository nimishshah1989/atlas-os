# atlas/simulation/strategies/runner.py
"""Nightly paper trading runner — called by scripts/m7_daily.py after Atlas compute.

Design:
- Fetch decisions ONCE per tier (3 DB calls), not once per strategy (15 calls)
- Loop 15 strategies in sequence, applying filter + computing trades per strategy
- Bulk-write all trades + performance rows
- Compute Jaccard overlap matrix (105 pairs) at end
- All sync (psycopg2, no asyncio)
"""

from __future__ import annotations

import gc
from datetime import date
from typing import Any
from uuid import UUID

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.simulation.core.overlap import jaccard_similarity, upper_triangle_pairs
from atlas.simulation.core.paper_trader import (
    MissingAtlasDecisionsError,
    apply_strategy_filter,
    check_decisions_exist,
    compute_trades,
    fetch_decisions,
    load_current_holdings,
    record_daily_performance,
    update_holdings,
    write_trades,
)
from atlas.simulation.strategies.loader import load_all_configs

log = structlog.get_logger()


def _get_regime(engine: Engine, today: date) -> str:
    """Fetch today's market regime from atlas_market_regime_daily."""
    with open_compute_session(engine) as conn:
        regime = conn.execute(
            text(
                "SELECT regime FROM atlas.atlas_market_regime_daily "
                "WHERE date = :d ORDER BY created_at DESC LIMIT 1"
            ),
            {"d": today},
        ).scalar()
    if regime is None:
        log.warning("runner_no_regime", date=str(today), fallback="Constructive")
        return "Constructive"
    return str(regime)


def _get_strategy_ids(engine: Engine) -> dict[str, UUID]:
    """Fetch {name: id} map from atlas.strategy_configs."""
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("SELECT id, name FROM atlas.strategy_configs WHERE is_active = TRUE")
        ).fetchall()
    return {r.name: UUID(str(r.id)) for r in rows}


def _get_prices_today(engine: Engine, today: date) -> dict[str, float]:
    """Fetch closing prices for today from JIP for use in trade notional values."""
    with open_compute_session(engine) as conn:
        rows = conn.execute(
            text("SELECT instrument_id, close FROM de_ohlcv_daily WHERE date = :d"),
            {"d": today},
        ).fetchall()
    return {r.instrument_id: float(r.close) for r in rows if r.close is not None}


def _compute_total_value(
    holdings: dict[str, Any],
    prices: dict[str, float],
    base_value: float = 10_000_000.0,
) -> float:
    """Compute portfolio total value from holdings + current prices."""
    if not holdings:
        return base_value
    total = sum(prices.get(iid) or h.notional_value for iid, h in holdings.items())
    return total if total > 0 else base_value


def _compute_overlap_matrix(
    engine: Engine,
    today: date,
    strategy_ids: dict[str, UUID],
    holdings_map: dict[str, dict[str, Any]],
) -> None:
    """Compute and write the 105-pair Jaccard overlap matrix for today."""
    ids = list(strategy_ids.values())
    id_to_name = {v: k for k, v in strategy_ids.items()}

    pairs = upper_triangle_pairs(ids)
    rows = []
    for a_id, b_id in pairs:
        a_name = id_to_name[a_id]
        b_name = id_to_name[b_id]
        a_instruments = set(holdings_map.get(a_name, {}).keys())
        b_instruments = set(holdings_map.get(b_name, {}).keys())
        j = jaccard_similarity(a_instruments, b_instruments)
        common = len(a_instruments & b_instruments)
        rows.append((today, str(a_id), str(b_id), j, common))

    if not rows:
        return

    sql = text("""
        INSERT INTO atlas.strategy_overlap_daily
            (date, strategy_a_id, strategy_b_id, jaccard_similarity, common_instruments)
        VALUES (:date, :a_id, :b_id, :jaccard, :common)
        ON CONFLICT (date, strategy_a_id, strategy_b_id) DO UPDATE SET
            jaccard_similarity = EXCLUDED.jaccard_similarity,
            common_instruments = EXCLUDED.common_instruments
    """)
    with open_compute_session(engine) as conn:
        for row_date, row_a, row_b, row_j, row_common in rows:
            conn.execute(
                sql,
                {
                    "date": row_date,
                    "a_id": row_a,
                    "b_id": row_b,
                    "jaccard": row_j,
                    "common": row_common,
                },
            )
        conn.commit()
    log.info("runner_overlap_written", pairs=len(rows), date=str(today))


def run_nightly(engine: Engine, today: date) -> dict[str, int]:
    """Run all 15 paper trading strategies for today.

    Returns: {strategy_name: trades_count}
    Raises: MissingAtlasDecisionsError if Atlas compute hasn't run yet.
    """
    log.info("runner_start", date=str(today))

    # Guard: verify Atlas decisions exist for today
    for tier in ("stocks", "etf", "fund"):
        try:
            check_decisions_exist(engine, tier, today)
        except MissingAtlasDecisionsError:
            log.warning("runner_no_decisions", tier=tier, date=str(today))

    regime = _get_regime(engine, today)
    strategy_ids = _get_strategy_ids(engine)
    prices = _get_prices_today(engine, today)
    configs = load_all_configs()

    log.info("runner_context", regime=regime, strategies=len(configs), date=str(today))

    # Fetch decisions ONCE per tier — 3 DB calls for all 15 strategies
    with open_compute_session(engine) as conn:
        decisions_stocks = fetch_decisions(conn, "stocks", today)
        decisions_etf = fetch_decisions(conn, "etf", today)
        decisions_fund = fetch_decisions(conn, "fund", today)

    log.info(
        "runner_decisions_fetched",
        stocks=len(decisions_stocks),
        etf=len(decisions_etf),
        fund=len(decisions_fund),
    )

    results: dict[str, int] = {}
    holdings_map: dict[str, dict[str, Any]] = {}

    for cfg in configs:
        strategy_id = strategy_ids.get(cfg.name)
        if strategy_id is None:
            log.warning("runner_strategy_not_in_db", name=cfg.name)
            continue

        # Select pre-fetched decisions for this strategy's tier
        if cfg.tier == "stocks_only":
            decisions = decisions_stocks
        elif cfg.tier == "fund_only":
            decisions = decisions_fund
        else:
            # blend: concat stocks + etf
            decisions = pd.concat([decisions_stocks, decisions_etf], ignore_index=True)

        # Load current holdings
        with open_compute_session(engine) as conn:
            holdings = load_current_holdings(conn, strategy_id)

        holdings_map[cfg.name] = holdings

        # Apply strategy filter (pure — no DB)
        entries, exits = apply_strategy_filter(decisions, cfg, cfg.threshold_overrides)

        # Compute trades (pure — no DB)
        trades = compute_trades(holdings, entries, exits, regime, cfg)

        # Write trades to DB
        write_trades(engine, trades, strategy_id, today, regime, prices)

        # Update holdings state
        update_holdings(engine, trades, strategy_id, today)

        # Reload holdings after trades for accurate position count
        with open_compute_session(engine) as conn:
            updated_holdings = load_current_holdings(conn, strategy_id)

        # Record daily performance
        total_value = _compute_total_value(updated_holdings, prices)
        record_daily_performance(
            engine=engine,
            strategy_id=strategy_id,
            today=today,
            total_value=total_value,
            daily_return=0.0,  # computed by metrics.py in Task 10
            regime=regime,
            positions_count=len(updated_holdings),
        )

        results[cfg.name] = len(trades)
        log.info(
            "runner_strategy_done",
            name=cfg.name,
            trades=len(trades),
            positions=len(updated_holdings),
        )

        # Free concat memory for blend strategies
        del decisions
        gc.collect()

    # Compute overlap matrix for today
    _compute_overlap_matrix(engine, today, strategy_ids, holdings_map)

    log.info("runner_complete", date=str(today), strategies=len(results))
    return results
