"""Point-in-time universe membership loader and filter.

Handles Nifty 500 membership state at any historical date for backtesting
and portfolio simulation. Reads from atlas.atlas_universe_membership_daily.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection

log = structlog.get_logger()


def build_membership_set(rows: list[dict]) -> dict:
    """Convert DB rows into {instrument_id: {date, ...}} for fast point-in-time lookup.

    Args:
        rows: List of dicts with 'instrument_id' and 'date' keys.

    Returns:
        Dict mapping instrument_id -> set of dates when instrument was a member.

    Example:
        >>> rows = [{"instrument_id": 1, "date": date(2024, 1, 1)}]
        >>> membership = build_membership_set(rows)
        >>> date(2024, 1, 1) in membership[1]
        True
    """
    result: dict = defaultdict(set)
    for row in rows:
        result[row["instrument_id"]].add(row["date"])
    return dict(result)


def filter_to_universe(
    instrument_ids: list,
    as_of_date: date,
    membership: dict,
) -> list:
    """Return only instrument_ids that were in the universe on as_of_date.

    Args:
        instrument_ids: List of instrument IDs to filter.
        as_of_date: Date to check membership for.
        membership: Dict from build_membership_set() or load_universe_membership().

    Returns:
        Filtered list preserving original order, containing only IDs that were
        members on as_of_date.

    Example:
        >>> membership = {1: {date(2024, 1, 1)}, 2: {date(2024, 1, 1), date(2024, 1, 2)}}
        >>> filter_to_universe([1, 2], date(2024, 1, 2), membership)
        [2]
    """
    return [iid for iid in instrument_ids if as_of_date in membership.get(iid, set())]


def load_universe_membership(
    conn: Connection,
    universe: str,
    start_date: date,
    end_date: date,
) -> dict:
    """Load point-in-time membership from atlas.atlas_universe_membership_daily.

    Args:
        conn: SQLAlchemy connection.
        universe: Universe name (e.g., 'nifty500').
        start_date: Inclusive start date.
        end_date: Inclusive end date.

    Returns:
        Dict mapping instrument_id -> set of dates when instrument was a member
        in the specified universe and date range.

    Logs:
        Info log with universe name, instrument count, and row count.
    """
    rows = (
        conn.execute(
            text(
                "SELECT instrument_id, date FROM atlas.atlas_universe_membership_daily "
                "WHERE universe = :universe AND was_member = TRUE "
                "AND date BETWEEN :start AND :end"
            ),
            {"universe": universe, "start": start_date, "end": end_date},
        )
        .mappings()
        .all()
    )

    membership = build_membership_set([dict(r) for r in rows])
    log.info(
        "universe_loaded",
        universe=universe,
        instruments=len(membership),
        rows=len(rows),
        start_date=str(start_date),
        end_date=str(end_date),
    )
    return membership


def bootstrap_nifty500_membership(conn: Connection) -> int:
    """Seed atlas.atlas_universe_membership_daily from atlas_universe_stocks for all dates.

    Initial approximation — assumes each instrument was a member for all dates
    it has price data. Replace with NSE historical composition files for
    survivorship-bias-free simulation.

    Args:
        conn: SQLAlchemy connection.

    Returns:
        Number of rows inserted.

    Logs:
        Info log with insertion count.
    """
    result = conn.execute(
        text(
            """
            INSERT INTO atlas.atlas_universe_membership_daily
                (instrument_id, date, universe, was_member)
            SELECT DISTINCT m.instrument_id, m.date, 'nifty500', TRUE
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_universe_stocks i ON i.instrument_id = m.instrument_id
            WHERE i.in_nifty_500 = TRUE
            ON CONFLICT (instrument_id, date, universe) DO NOTHING
            """
        )
    )
    count = result.rowcount
    log.info("universe_bootstrapped", inserted=count)
    return count
