# ruff: noqa: S608  -- entire file uses a closed whitelist; no user input reaches SQL
"""SQL source-of-truth lookups for Phase C route crawler.

Closed whitelist of ~30 entity_type.field → SQL query mappings.
No free-form query construction from user or DOM input.

``lookup(validator_id, conn)`` parses the validator_id string
(format: ``{entity_type}.{field}:{pk_value}``) and returns the
backend ``Decimal | str | None`` for diff comparison.

PK values come from DOM attributes, NOT from user input, but they
are still sanitised via ``_esc()`` before embedding in SQL literals
(defence-in-depth: validator_id format is attacker-controlled if DOM
is compromised).

All queries are parameterised or use ``_esc()``-sanitised literals on
whitelisted identifier slots.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

# ---------------------------------------------------------------------------
# PK sanitiser — allow only alphanumeric, underscore, dash, dot, comma, space
# ---------------------------------------------------------------------------

_SAFE_PK_RE = re.compile(r"^[\w\s.,\-&]+$")


def _esc(pk_value: str) -> str:
    """Raise ValueError if pk_value contains characters outside the safe set."""
    if not _SAFE_PK_RE.match(pk_value):
        raise ValueError(
            f"Unsafe pk_value in data-validator-id: {pk_value!r}. "
            "Only alphanumeric, underscore, dash, dot, comma, ampersand, and space allowed."
        )
    return pk_value


# ---------------------------------------------------------------------------
# Query factory type
# ---------------------------------------------------------------------------

QueryFn = Callable[[Connection, str], "Decimal | str | None"]


def _scalar_result(row_val: object) -> Decimal | str | None:
    """Convert a DB row value to Decimal (numeric) or str (categorical)."""
    if row_val is None:
        return None
    if isinstance(row_val, int | float):
        return Decimal(str(row_val))
    return row_val  # type: ignore[return-value]


def _stock_scalar(column: str) -> QueryFn:
    """Return a QueryFn that fetches one column from atlas_stock_metrics_daily."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        parts = [p.strip() for p in pk.split(",", 1)]
        instrument_id = _esc(parts[0])
        date_clause = f"AND date = '{_esc(parts[1])}'" if len(parts) > 1 else ""
        sql = text(
            f"SELECT {column} FROM atlas.atlas_stock_metrics_daily "
            f"WHERE instrument_id = '{instrument_id}' {date_clause} "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


def _conviction_scalar(column: str) -> QueryFn:
    """Fetch one column from atlas_stock_conviction_daily."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        parts = [p.strip() for p in pk.split(",", 1)]
        instrument_id = _esc(parts[0])
        date_clause = f"AND date = '{_esc(parts[1])}'" if len(parts) > 1 else ""
        sql = text(
            f"SELECT {column} FROM atlas.atlas_stock_conviction_daily "
            f"WHERE instrument_id = '{instrument_id}' {date_clause} "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


def _sector_scalar(column: str) -> QueryFn:
    """Fetch one column from atlas_sector_metrics_daily (PK: sector_name)."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        parts = [p.strip() for p in pk.split(",", 1)]
        sector = _esc(parts[0])
        date_clause = f"AND date = '{_esc(parts[1])}'" if len(parts) > 1 else ""
        sql = text(
            f"SELECT {column} FROM atlas.atlas_sector_metrics_daily "
            f"WHERE sector_name = '{sector}' {date_clause} "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


def _sector_state_scalar(column: str) -> QueryFn:
    """Fetch one column from atlas_sector_states_daily (PK: sector_name)."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        parts = [p.strip() for p in pk.split(",", 1)]
        sector = _esc(parts[0])
        date_clause = f"AND date = '{_esc(parts[1])}'" if len(parts) > 1 else ""
        sql = text(
            f"SELECT {column} FROM atlas.atlas_sector_states_daily "
            f"WHERE sector_name = '{sector}' {date_clause} "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


def _etf_scalar(column: str) -> QueryFn:
    """Fetch one column from atlas_etf_metrics_daily. PK is ticker."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        parts = [p.strip() for p in pk.split(",", 1)]
        ticker = _esc(parts[0])
        date_clause = f"AND date = '{_esc(parts[1])}'" if len(parts) > 1 else ""
        sql = text(
            f"SELECT {column} FROM atlas.atlas_etf_metrics_daily "
            f"WHERE ticker = '{ticker}' {date_clause} "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


def _fund_scalar(column: str) -> QueryFn:
    """Fetch one column from atlas_fund_lens_daily. PK is mstar_id."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        parts = [p.strip() for p in pk.split(",", 1)]
        mstar_id = _esc(parts[0])
        date_clause = f"AND date = '{_esc(parts[1])}'" if len(parts) > 1 else ""
        sql = text(
            f"SELECT {column} FROM atlas.atlas_fund_lens_daily "
            f"WHERE mstar_id = '{mstar_id}' {date_clause} "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


def _regime_scalar(column: str) -> QueryFn:
    """Fetch one column from atlas_market_regime_daily."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        date_val = _esc(pk.strip())
        sql = text(
            f"SELECT {column} FROM atlas.atlas_market_regime_daily "
            f"WHERE date = '{date_val}' "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


def _stock_state_scalar(column: str) -> QueryFn:
    """Fetch one column from atlas_stock_states_daily."""

    def _fn(conn: Connection, pk: str) -> Decimal | str | None:
        parts = [p.strip() for p in pk.split(",", 1)]
        instrument_id = _esc(parts[0])
        date_clause = f"AND date = '{_esc(parts[1])}'" if len(parts) > 1 else ""
        sql = text(
            f"SELECT {column} FROM atlas.atlas_stock_states_daily "
            f"WHERE instrument_id = '{instrument_id}' {date_clause} "
            f"ORDER BY date DESC LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        return _scalar_result(row[0] if row else None)

    return _fn


# ---------------------------------------------------------------------------
# Closed whitelist: entity_type.field → QueryFn
# ---------------------------------------------------------------------------

LOOKUPS: dict[str, QueryFn] = {
    # Stock conviction
    "stock.conviction_score": _conviction_scalar("conviction_score"),
    "stock.backing_ic": _conviction_scalar("backing_ic"),
    # Stock metrics — RS pctiles
    "stock.rs_pctile_3m": _stock_scalar("rs_pctile_3m"),
    "stock.rs_pctile_1m": _stock_scalar("rs_pctile_1m"),
    "stock.rs_pctile_1w": _stock_scalar("rs_pctile_1w"),
    # Stock metrics — velocity
    "stock.rs_velocity": _stock_scalar("rs_velocity"),
    # Stock metrics — returns
    "stock.ret_1w": _stock_scalar("ret_1w"),
    "stock.ret_1m": _stock_scalar("ret_1m"),
    "stock.ret_3m": _stock_scalar("ret_3m"),
    "stock.ret_6m": _stock_scalar("ret_6m"),
    # Stock metrics — moving averages / participation
    "stock.above_30w_ma": _stock_scalar("above_30w_ma"),
    "stock.participation_rs": _stock_scalar("participation_rs"),
    # Stock states
    "stock.momentum_state": _stock_state_scalar("momentum_state"),
    "stock.rs_state": _stock_state_scalar("rs_state"),
    # Sector state (atlas_sector_states_daily — separate table)
    "sector.sector_state": _sector_state_scalar("sector_state"),
    # Sector metrics (atlas_sector_metrics_daily)
    "sector.rs_velocity": _sector_scalar("rs_velocity"),
    "sector.participation_rs": _sector_scalar("participation_rs"),
    "sector.rs_pctile_cross_sector": _sector_scalar("rs_pctile_cross_sector"),
    # ETF metrics
    "etf.rs_pctile_3m": _etf_scalar("rs_pctile_3m"),
    "etf.effort_ratio_63": _etf_scalar("effort_ratio_63"),
    "etf.above_30w_ma": _etf_scalar("above_30w_ma"),
    "etf.rs_state": _etf_scalar("rs_state"),
    # Fund metrics
    "fund.rs_pctile_3m": _fund_scalar("rs_pctile_3m"),
    "fund.category_state": _fund_scalar("category_state"),
    "fund.nav_state": _fund_scalar("nav_state"),
    "fund.composition_state": _fund_scalar("composition_state"),
    # Market regime
    "regime.regime_state": _regime_scalar("regime_state"),
    "regime.breadth_score": _regime_scalar("breadth_score"),
    "regime.deployment_multiplier": _regime_scalar("deployment_multiplier"),
    "regime.india_vix": _regime_scalar("india_vix"),
    "regime.pct_above_ema_50": _regime_scalar("pct_above_ema_50"),
    "regime.ad_ratio": _regime_scalar("ad_ratio"),
    "regime.mcclellan_oscillator": _regime_scalar("mcclellan_oscillator"),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lookup(validator_id: str, conn: Connection) -> Decimal | str | None:
    """Fetch the backend source-of-truth value for a ``data-validator-id``.

    Args:
        validator_id: Format ``{entity_type}.{field}:{pk_value}``.
                      e.g. ``"stock.conviction_score:RELIANCE"``
                      e.g. ``"sector.sector_state:Information Technology"``
        conn: Live SQLAlchemy connection.

    Returns:
        Backend value as ``Decimal``, ``str``, or ``None``.

    Raises:
        ValueError: If validator_id format is wrong or entity_type.field
                    is not in the whitelist.
    """
    if ":" not in validator_id:
        raise ValueError(
            f"Invalid data-validator-id format {validator_id!r}. "
            "Expected '{entity_type}.{field}:{pk_value}'."
        )

    field_key, pk_value = validator_id.split(":", 1)
    field_key = field_key.strip()

    query_fn = LOOKUPS.get(field_key)
    if query_fn is None:
        raise ValueError(
            f"No SQL lookup registered for field key {field_key!r}. Known keys: {sorted(LOOKUPS)}"
        )

    return query_fn(conn, pk_value.strip())
