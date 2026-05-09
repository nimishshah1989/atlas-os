# atlas/simulation/custom/builder.py
"""Custom portfolio validation and optional weight suggestion (PyPortfolioOpt).

validate_custom_portfolio() is the primary entry point. It runs 4 checks and
raises ValueError for each violation. Universe lookup uses parameterized SQL —
never f-string interpolation of user instrument_ids.

Note on SQL style: all CAST(col AS type) forms are used instead of col::type
to avoid the SQLAlchemy text() param-cast collision bug (::type near :param).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session

log = structlog.get_logger()

_MAX_INSTRUMENTS = 30
_WEIGHT_SUM_TOLERANCE = 0.01  # ±0.01% tolerance


@dataclass
class InstrumentWeight:
    instrument_id: str
    instrument_type: str  # 'stock' | 'etf' | 'fund'
    weight_pct: float  # percentage 0–100; float is intentional (ratio, not monetary amount)


def validate_custom_portfolio(
    instruments: list[InstrumentWeight],
    engine: Engine,
) -> None:
    """Validate a custom portfolio before saving.

    Raises ValueError with a descriptive message for each violation:
    - Empty list
    - More than 30 instruments
    - Duplicate instrument_ids
    - Weights don't sum to 100 ± 0.01
    - Any instrument not in Atlas universe (using most recent decision date)
    """
    if not instruments:
        raise ValueError("Portfolio must contain at least 1 instrument.")

    if len(instruments) > _MAX_INSTRUMENTS:
        raise ValueError(
            f"Portfolio exceeds {_MAX_INSTRUMENTS} instruments ({len(instruments)} given). "
            "Max 30 instruments for custom portfolios."
        )

    ids = [i.instrument_id for i in instruments]
    if len(ids) != len(set(ids)):
        seen: set[str] = set()
        dupes = [i for i in ids if i in seen or seen.add(i)]  # type: ignore[func-returns-value]
        raise ValueError(f"Portfolio contains duplicate instrument IDs: {dupes}")

    total_weight = sum(i.weight_pct for i in instruments)
    if abs(total_weight - 100.0) > _WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"Portfolio weights must sum to 100% ± {_WEIGHT_SUM_TOLERANCE}%. "
            f"Got {total_weight:.4f}%."
        )

    _validate_universe_membership(instruments, engine)


def _validate_universe_membership(instruments: list[InstrumentWeight], engine: Engine) -> None:
    """Check all instruments exist in the appropriate universe table.

    Branches by instrument_type:
    - 'stock' → atlas_stock_decisions_daily (most recent date)
    - 'etf'   → atlas_universe_etfs (ticker — instrument_id field stores ticker)
    - 'fund'  → atlas_universe_funds (mstar_id — instrument_id field stores mstar_id)

    Groups instruments by type to minimise SQL round-trips. Uses ANY(:ids) with a
    list parameter — no f-string interpolation of user input.

    Note: CAST(instrument_id AS text) used throughout — not instrument_id::text —
    to avoid the SQLAlchemy text() param-cast collision with :ids parameter.
    """
    by_type: dict[str, list[str]] = {}
    for inst in instruments:
        by_type.setdefault(inst.instrument_type, []).append(inst.instrument_id)

    with open_compute_session(engine) as conn:
        for itype, ids in by_type.items():
            if itype == "stock":
                ref_date = conn.execute(
                    text("SELECT MAX(date) FROM atlas.atlas_stock_decisions_daily")
                ).scalar()

                if ref_date is None:
                    raise ValueError(
                        "Cannot validate universe membership: "
                        "atlas_stock_decisions_daily is empty. "
                        "Ensure M3 backfill has run before creating custom portfolios."
                    )

                rows = conn.execute(
                    text("""
                        SELECT CAST(instrument_id AS text)
                        FROM atlas.atlas_stock_decisions_daily
                        WHERE date = :ref_date
                          AND CAST(instrument_id AS text) = ANY(:ids)
                    """),
                    {"ref_date": ref_date, "ids": ids},
                ).fetchall()
            elif itype == "etf":
                rows = conn.execute(
                    text("""
                        SELECT ticker
                        FROM atlas.atlas_universe_etfs
                        WHERE ticker = ANY(:ids)
                          AND effective_to IS NULL
                    """),
                    {"ids": ids},
                ).fetchall()
            elif itype == "fund":
                rows = conn.execute(
                    text("""
                        SELECT mstar_id
                        FROM atlas.atlas_universe_funds
                        WHERE mstar_id = ANY(:ids)
                          AND effective_to IS NULL
                    """),
                    {"ids": ids},
                ).fetchall()
            else:
                raise ValueError(f"unknown instrument_type: {itype}")

            found = {r[0] for r in rows}
            missing = set(ids) - found
            if missing:
                raise ValueError(
                    f"The following {itype} instruments are not in the Atlas universe: "
                    f"{sorted(missing)}"
                )


def suggest_min_variance_weights(
    instruments: list[InstrumentWeight],
    engine: Engine,
    lookback_days: int = 252,
) -> list[InstrumentWeight]:
    """Suggest minimum-variance weights using PyPortfolioOpt.

    Only available for portfolios with ≤ 30 instruments. Falls back to equal
    weights if PyPortfolioOpt is unavailable or price data is insufficient.
    Uses JIP equity price history for covariance estimation.
    """
    if len(instruments) > _MAX_INSTRUMENTS:
        log.info("builder_suggest_equal_weight", reason="over_30_instruments")
        equal_w = round(100.0 / len(instruments), 4)
        return [InstrumentWeight(i.instrument_id, i.instrument_type, equal_w) for i in instruments]

    ids = [i.instrument_id for i in instruments]
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            text("""
                SELECT date, CAST(instrument_id AS text) AS instrument_id, close
                FROM de_equity_ohlcv
                WHERE CAST(instrument_id AS text) = ANY(:ids)
                  AND date BETWEEN :start AND :end
                ORDER BY date, instrument_id
            """),
            conn,
            params={"ids": ids, "start": start_date, "end": end_date},
        )

    if df.empty:
        log.warning("builder_suggest_no_prices", instruments=ids)
        equal_w = round(100.0 / len(instruments), 4)
        return [InstrumentWeight(i.instrument_id, i.instrument_type, equal_w) for i in instruments]

    price_pivot = df.pivot(index="date", columns="instrument_id", values="close").dropna()

    try:
        from pypfopt import EfficientFrontier, expected_returns, risk_models

        mu = expected_returns.mean_historical_return(price_pivot, frequency=252)
        cov_matrix = risk_models.sample_cov(price_pivot, frequency=252)
        ef = EfficientFrontier(mu, cov_matrix)
        ef.min_volatility()
        cleaned = ef.clean_weights()
    except Exception:
        log.warning("builder_pypfopt_failed", instruments=ids, exc_info=True)
        equal_w = round(100.0 / len(instruments), 4)
        return [InstrumentWeight(i.instrument_id, i.instrument_type, equal_w) for i in instruments]

    result = []
    for inst in instruments:
        w = float(cleaned.get(inst.instrument_id, 0.0)) * 100.0
        result.append(InstrumentWeight(inst.instrument_id, inst.instrument_type, round(w, 4)))

    return result
