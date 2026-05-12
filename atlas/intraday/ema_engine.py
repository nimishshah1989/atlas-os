"""Incremental EMA-20 and EMA-50 engine for intraday state.

Bootstrap loads from atlas_stock_metrics_daily (columns: ema_20_stock,
ema_50_stock). Subsequent updates are pure Decimal arithmetic per bar close.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

import psycopg2
import structlog

log = structlog.get_logger()


class EMAState(NamedTuple):
    """Holds the current EMA-20 and EMA-50 values for one instrument."""

    ema_20: Decimal
    ema_50: Decimal


def compute_k(period: int) -> Decimal:
    """Return the EMA smoothing factor k = 2 / (period + 1).

    Args:
        period: EMA period (e.g. 20, 50).

    Returns:
        Decimal smoothing factor in range (0, 1).
    """
    return Decimal(2) / (Decimal(period) + Decimal(1))


def update_ema(close: Decimal, state: EMAState) -> EMAState:
    """Apply one incremental EMA update using the standard formula.

    EMA_new = close × k + EMA_old × (1 − k)

    Args:
        close: Bar close price as Decimal.
        state: Current EMAState (ema_20, ema_50) to update.

    Returns:
        New EMAState with updated ema_20 and ema_50.
    """
    k20 = compute_k(20)
    k50 = compute_k(50)

    new_ema_20 = close * k20 + state.ema_20 * (Decimal(1) - k20)
    new_ema_50 = close * k50 + state.ema_50 * (Decimal(1) - k50)

    return EMAState(ema_20=new_ema_20, ema_50=new_ema_50)


def _strip_dialect(conn_str: str) -> str:
    """Strip SQLAlchemy dialect prefix for raw psycopg2 connections."""
    if conn_str.startswith("postgresql+psycopg2://"):
        return conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)
    return conn_str


def bootstrap_ema_state(*, conn_str: str) -> dict[str, EMAState]:
    """Load the most-recent EMA values from atlas_stock_metrics_daily.

    Queries for the latest date and returns one EMAState per instrument.
    If the ema_20_stock or ema_50_stock columns do not exist (e.g. new DB),
    logs a warning and returns an empty dict. The ingester will bootstrap
    EMA from the first bar close instead.

    Args:
        conn_str: DSN for the atlas database.

    Returns:
        Dict mapping instrument_id (UUID string) → EMAState.
    """
    dsn = _strip_dialect(conn_str)
    conn = psycopg2.connect(dsn)  # type: ignore[attr-defined]
    try:
        with conn.cursor() as cur:
            # Check that the required columns exist before querying
            cur.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'atlas'
                  AND table_name = 'atlas_stock_metrics_daily'
                  AND column_name IN ('ema_20_stock', 'ema_50_stock')
                """
            )
            col_count: int = cur.fetchone()[0]  # type: ignore[index]
            if col_count < 2:
                log.warning(
                    "ema_bootstrap_columns_missing",
                    found_cols=col_count,
                    expected_cols=2,
                    note="Ingester will bootstrap EMA from first bar close",
                )
                return {}

            cur.execute(
                """
                SELECT instrument_id::text, ema_20_stock, ema_50_stock
                FROM atlas.atlas_stock_metrics_daily
                WHERE date = (
                    SELECT MAX(date)
                    FROM atlas.atlas_stock_metrics_daily
                )
                  AND ema_20_stock IS NOT NULL
                  AND ema_50_stock IS NOT NULL
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    result: dict[str, EMAState] = {}
    for instrument_id_str, ema_20_raw, ema_50_raw in rows:
        # psycopg2 returns Decimal for NUMERIC columns already; cast to be explicit
        result[instrument_id_str] = EMAState(
            ema_20=Decimal(str(ema_20_raw)),
            ema_50=Decimal(str(ema_50_raw)),
        )

    row_count = len(result)
    log.info("ema_bootstrap_complete", instrument_count=row_count)
    return result
