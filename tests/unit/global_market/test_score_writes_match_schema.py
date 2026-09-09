"""Every column the P2 writers emit is a column the table actually has.

There is no database in CI, so an upsert naming a column that does not exist cannot be caught
by running it — it is caught at 01:00 on the box, by the FM, as a failed nightly step. This
closes that gap the only way it can be closed without Postgres: build the frame the writer
would send, and check its columns against the CREATE TABLE the migration applies.

This is the same class of check as ``test_country_report.py`` (the report header vs the emitted
row) and ``test_producer_registry.py`` (a guarded table vs a cron step): two constants in this
repo that must agree, asserted directly rather than discovered in production.

Rule #0: no market data. Every metric below is NaN — which is not an invented number, it is
exactly what the query returns for a fund whose metric has not been computed — and the
assertions are about column NAMES, not values.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tests.unit.global_market.script_loader import load_global_script

pytestmark = pytest.mark.unit

DDL = Path(__file__).resolve().parents[3] / "scripts" / "global_market" / "ddl"
classify_etfs = load_global_script("classify_etfs")
score_etfs = load_global_script("score_etfs")
seed_thresholds = load_global_script("seed_thresholds")

# The metric columns TARGETS_SQL selects and the scorer reads. Kept here as the list the test
# builds its frame from; a column the query stops selecting makes the scorer raise KeyError
# here rather than on the box.
METRIC_COLUMNS = (
    "ema_21",
    "ema_50",
    "ema_200",
    "rsi_14",
    "ret_1w",
    "ret_6m",
    "rs_3m_spy",
    "rs_6m_spy",
    "rs_12m_spy",
    "vol_63d_ann",
    "mdd_12m",
    "downside_dev_63d",
    "beta_spy_252",
    "adv_usd_60d_median",
    "price",
)


def table_columns(filename: str, table: str) -> set[str]:
    """The column names of one CREATE TABLE in a DDL file."""
    sql = (DDL / filename).read_text()
    start = sql.lower().index(f"create table if not exists atlas_global.{table}")
    body = sql[sql.index("(", start) : sql.index("\n);", start)]
    names: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip().lstrip("(").strip()
        if not stripped or stripped.startswith("--"):
            continue
        if re.match(r"(?i)^(primary key|constraint|unique|check|foreign|references)", stripped):
            continue
        match = re.match(r"^([a-z_][a-z0-9_]*)\s", stripped)
        if match:
            names.add(match.group(1))
    return names


@pytest.fixture(scope="module")
def thresholds() -> dict[str, Decimal]:
    return {
        str(row["threshold_key"]): Decimal(str(row["threshold_value"]))
        for row in seed_thresholds.SEEDS
    }


def test_the_ddl_parser_finds_a_plausible_table() -> None:
    """If the parser silently matched nothing, every assertion below would pass vacuously."""
    columns = table_columns("05_scores.sql", "etf_scores_daily")
    assert {"instrument_id", "date", "composite", "peer_group"} <= columns
    assert len(columns) > 25


def test_score_etfs_writes_only_columns_etf_scores_daily_has(
    thresholds: dict[str, Decimal],
) -> None:
    frame = pd.DataFrame(
        {
            "instrument_id": ["00000000-0000-0000-0000-000000000000"],
            "symbol": ["EWJ"],
            "name": ["iShares MSCI Japan ETF"],
            "asset_class": ["equity"],
            "strategy": ["country"],
            "peer_group": ["equity:country"],
            "asset_group": ["equity"],
            "grouped_by": ["strategy"],
            "peer_n": [34],
            "peer_pct_6m": [float("nan")],
            "vol_pct": [float("nan")],
            "mdd_pct": [float("nan")],
            "downside_pct": [float("nan")],
            **{c: [float("nan")] for c in METRIC_COLUMNS},
        }
    )
    table, lines = score_etfs.score_rows(frame, dt.date(2026, 9, 8), thresholds, "run")
    written = set(table.columns)
    allowed = table_columns("05_scores.sql", "etf_scores_daily")
    assert written <= allowed, (
        f"score_etfs would send columns etf_scores_daily does not have: {sorted(written - allowed)}"
    )
    assert set(score_etfs.KEY) <= written, "the upsert key must be in the frame"
    assert len(lines) == 1 and len(lines[0]) == len(score_etfs.REPORT_COLUMNS)


def test_classify_etfs_writes_only_columns_etf_classification_has() -> None:
    frame = pd.DataFrame(
        {
            "instrument_id": ["00000000-0000-0000-0000-000000000000"],
            "symbol": ["EWJ"],
            "name": ["iShares MSCI Japan ETF"],
        }
    )
    table, lines = classify_etfs.rows(frame, set(), dt.datetime(2026, 9, 8, tzinfo=dt.UTC))
    written = set(table.columns)
    allowed = table_columns("03_classification.sql", "etf_classification")
    assert written <= allowed, (
        f"classify_etfs would send columns etf_classification does not have: "
        f"{sorted(written - allowed)}"
    )
    assert set(classify_etfs.KEY) <= written
    assert len(lines) == 1 and len(lines[0]) == len(classify_etfs.REPORT_COLUMNS)


def test_a_fund_with_no_metrics_still_produces_a_writable_row(
    thresholds: dict[str, Decimal],
) -> None:
    """The nightly must not fall over on a fund listed this week. Every lens is None, the
    composite is None, and the row is still shaped for the upsert — the board then shows it
    unscored rather than the whole step failing."""
    frame = pd.DataFrame(
        {
            "instrument_id": ["00000000-0000-0000-0000-000000000000"],
            "symbol": ["NEWF"],
            "name": ["A fund listed this week"],
            "asset_class": [None],
            "strategy": [None],
            "peer_group": ["unclassified"],
            "asset_group": ["unclassified"],
            "grouped_by": ["asset_class"],
            "peer_n": [1],
            "peer_pct_6m": [float("nan")],
            "vol_pct": [float("nan")],
            "mdd_pct": [float("nan")],
            "downside_pct": [float("nan")],
            **{c: [float("nan")] for c in METRIC_COLUMNS},
        }
    )
    table, _ = score_etfs.score_rows(frame, dt.date(2026, 9, 8), thresholds, "run")
    row = table.iloc[0]
    assert row["composite"] is None
    assert row["technical"] is None
    assert row["lenses_active"] == 0
