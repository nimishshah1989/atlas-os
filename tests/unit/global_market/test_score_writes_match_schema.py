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


def not_null_columns(filename: str, table: str) -> set[str]:
    """The columns one CREATE TABLE declares NOT NULL. A writer that sends None for any of them
    fails the whole upsert on the box — never in CI, which has no database.

    This is the shape of the bug that took out the first live nightly: ``classify_etfs`` wrote
    an explicit None into ``country_codes text[] NOT NULL DEFAULT '{}'``, and a DEFAULT does not
    save you — a default fills a column the INSERT omits, not one it names with a NULL. So the
    step died on its first row and score_etfs, freshness_guard and gate C all failed behind it.
    """
    sql = (DDL / filename).read_text()
    start = sql.lower().index(f"create table if not exists atlas_global.{table}")
    body = sql[sql.index("(", start) : sql.index("\n);", start)]
    names: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip().lstrip("(").strip().rstrip(",")
        if not stripped or stripped.startswith("--"):
            continue
        if re.match(r"(?i)^(primary key|constraint|unique|check|foreign|references)", stripped):
            continue
        match = re.match(r"^([a-z_][a-z0-9_]*)\s+(.*)$", stripped)
        if match and re.search(r"(?i)\bnot\s+null\b", match.group(2).split("--")[0]):
            names.add(match.group(1))
    return names


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


# ── no writer sends NULL into a NOT NULL column ───────────────────────────────


def assert_no_null_in_a_not_null_column(table: pd.DataFrame, filename: str, name: str) -> None:
    """Every value the writer would send for a NOT NULL column is a value, on every row."""
    required = not_null_columns(filename, name) & set(table.columns)
    assert required, f"parsed no NOT NULL columns for {name} — the check would pass vacuously"
    # bool(...) around .any(): on an object column holding lists pandas returns a numpy bool
    # that pyright will not accept as a conditional, and `isna` is element-wise, so an empty
    # list reads as present (which is the whole point) while a None reads as missing.
    offending = sorted(c for c in required if bool(table[c].isna().any()))
    assert not offending, (
        f"{name} would send NULL in NOT NULL column(s) {offending} — the upsert fails on the "
        f"box at 01:00, and every step downstream of it fails with it"
    )


def test_the_not_null_parser_finds_the_columns_that_actually_are() -> None:
    """Guards the guard: a parser that matched nothing would make every check below vacuous,
    and a parser that matched everything would make them all fail for the wrong reason."""
    required = not_null_columns("03_classification.sql", "etf_classification")
    assert {"instrument_id", "version", "country_codes", "classified_by", "status"} <= required
    assert "confidence" not in required and "rationale" not in required


def test_classify_etfs_sends_no_null_into_a_not_null_column() -> None:
    """The regression test for the first live nightly failure. Both no-country branches are
    exercised: a fund whose name states a country, and one whose name states none."""
    frame = pd.DataFrame(
        {
            "instrument_id": ["00000000-0000-0000-0000-000000000000"] * 2,
            "symbol": ["EWJ", "AAA"],
            # AAA is the real fund the box died on — its name states no country at all.
            "name": [
                "iShares MSCI Japan ETF",
                "Alternative Access First Priority CLO Bond ETF",
            ],
        }
    )
    table, _ = classify_etfs.rows(frame, set(), dt.datetime(2026, 9, 8, tzinfo=dt.UTC))
    assert_no_null_in_a_not_null_column(table, "03_classification.sql", "etf_classification")
    assert list(table["country_codes"]) == [["JP"], []]


def test_score_etfs_sends_no_null_into_a_not_null_column(
    thresholds: dict[str, Decimal],
) -> None:
    """The fund with no metrics at all is the worst case: every lens is None and the composite
    is None, and the row must STILL be writable — those columns are nullable by design, and the
    keys around them are not."""
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
    assert_no_null_in_a_not_null_column(table, "05_scores.sql", "etf_scores_daily")


# ── the percentile transform: alignment is the thing that fails silently ──────


def test_percentiles_are_cut_within_the_group_and_land_on_the_right_row() -> None:
    """The failure this guards is invisible by construction: if a group-wise percentile is
    misaligned, every fund gets some OTHER fund's percentile, every score stays inside 0-100,
    and no gate can tell. The frame below interleaves two groups deliberately, so a transform
    that grouped correctly but reassembled wrongly would put A's rank on B's row.

    The inputs are orderings, not market observations: what is asserted is that the best row
    in each group ranks 1.0 and the worst 0.0, whatever the values are (rule #0).
    """
    frame = pd.DataFrame(
        {
            # rows alternate between the two groups, and the groups' value ranges overlap —
            # so ranking globally instead of per-group gives visibly different answers.
            "peer_group": ["equity:sector", "equity:country"] * 3,
            "asset_group": ["equity"] * 6,
            "ret_6m": [0.10, 0.30, 0.20, 0.40, 0.30, 0.50],
            # add_percentiles ranks the three risk measures too; they are not what this test
            # asserts, but leaving them out would make it fail for the wrong reason.
            "vol_63d_ann": [0.10] * 6,
            "mdd_12m": [-0.10] * 6,
            "downside_dev_63d": [0.05] * 6,
        }
    )
    out = score_etfs.add_percentiles(frame)
    sector = out.loc[out["peer_group"] == "equity:sector", "peer_pct_6m"].tolist()
    country = out.loc[out["peer_group"] == "equity:country", "peer_pct_6m"].tolist()
    assert sector == [pytest.approx(1 / 3), pytest.approx(2 / 3), pytest.approx(1.0)]
    assert country == [pytest.approx(1 / 3), pytest.approx(2 / 3), pytest.approx(1.0)]


def test_a_missing_metric_gets_no_percentile_rather_than_the_bottom_of_its_group() -> None:
    frame = pd.DataFrame(
        {
            "peer_group": ["equity:sector"] * 3,
            "asset_group": ["equity"] * 3,
            "ret_6m": [0.10, float("nan"), 0.30],
            "vol_63d_ann": [0.10, 0.20, float("nan")],
            "mdd_12m": [-0.05, -0.40, -0.10],
            "downside_dev_63d": [0.05, 0.10, 0.15],
        }
    )
    out = score_etfs.add_percentiles(frame)
    assert pd.isna(out["peer_pct_6m"].iloc[1]), "no 6m return → no peer percentile"
    assert pd.isna(out["vol_pct"].iloc[2]), "no volatility → no volatility percentile"


def test_low_volatility_and_a_shallow_drawdown_are_the_good_end() -> None:
    """Getting either orientation backwards would rank the wildest fund safest, and every
    downstream number would still look perfectly reasonable."""
    frame = pd.DataFrame(
        {
            "peer_group": ["equity:sector"] * 2,
            "asset_group": ["equity"] * 2,
            "ret_6m": [0.10, 0.20],
            "vol_63d_ann": [0.10, 0.40],  # the first fund is calmer
            "mdd_12m": [-0.05, -0.40],  # the first fund fell less
            "downside_dev_63d": [0.05, 0.20],
        }
    )
    out = score_etfs.add_percentiles(frame)
    assert out["vol_pct"].iloc[0] > out["vol_pct"].iloc[1]
    assert out["mdd_pct"].iloc[0] > out["mdd_pct"].iloc[1]
    assert out["downside_pct"].iloc[0] > out["downside_pct"].iloc[1]
