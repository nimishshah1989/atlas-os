"""Per-table freshness snapshot for the health dashboard.

For each atlas.* table tracked, returns: row_count, latest_data_date, lag_days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session

# (table_name, date_column) — date_column is None for static tables (no time).
TRACKED_TABLES: tuple[tuple[str, str | None], ...] = (
    ("atlas.atlas_index_metrics_daily", "date"),
    ("atlas.atlas_sector_metrics_daily", "date"),
    ("atlas.atlas_sector_states_daily", "date"),
    ("atlas.atlas_market_regime_daily", "date"),
    ("atlas.atlas_stock_metrics_daily", "date"),
    ("atlas.atlas_stock_states_daily", "date"),
    ("atlas.atlas_etf_metrics_daily", "date"),
    ("atlas.atlas_etf_states_daily", "date"),
    ("atlas.atlas_fund_metrics_daily", "nav_date"),
    ("atlas.atlas_fund_lens_monthly", "as_of_date"),
    ("atlas.atlas_fund_states_daily", "date"),
    ("atlas.atlas_stock_decisions_daily", "date"),
    ("atlas.atlas_etf_decisions_daily", "date"),
    ("atlas.atlas_fund_decisions_daily", "date"),
)


@dataclass(frozen=True)
class TableFreshness:
    table_name: str
    row_count: int
    latest_date: date | None
    lag_days: int | None


def snapshot(engine: Engine, *, today: date | None = None) -> list[TableFreshness]:
    """Return freshness for every tracked atlas table.

    ``today`` defaults to today's UTC date — pass explicitly for testing.
    Lag is None when ``date_column`` is None or when the table is empty.
    """
    today = today or datetime.now(UTC).date()
    results: list[TableFreshness] = []

    with open_compute_session(engine) as conn:
        for table, date_col in TRACKED_TABLES:
            cnt_sql = f"SELECT count(*) AS c FROM {table}"  # noqa: S608 -- table from TRACKED_TABLES constant
            cnt = int(pd.read_sql(cnt_sql, conn).iloc[0]["c"])

            latest: date | None = None
            lag: int | None = None
            if date_col is not None and cnt > 0:
                row = pd.read_sql(f"SELECT MAX({date_col}) AS d FROM {table}", conn).iloc[0]  # noqa: S608 -- table/col from TRACKED_TABLES constant
                d = row["d"]
                if d is not None:
                    latest_date = pd.to_datetime(d).date()
                    latest = latest_date
                    lag = (today - latest_date).days

            results.append(
                TableFreshness(
                    table_name=table.split(".", 1)[-1],
                    row_count=cnt,
                    latest_date=latest,
                    lag_days=lag,
                )
            )
    return results


def lag_threshold_days(table_name: str) -> int:
    """Acceptable freshness lag for a table.

    Daily-cadence tables: 2 trading days.
    Monthly: 35 calendar days (next disclosure expected within ~30).
    """
    if table_name == "atlas_fund_lens_monthly":
        return 35
    return 2


__all__ = ["TRACKED_TABLES", "TableFreshness", "lag_threshold_days", "snapshot"]
