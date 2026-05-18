"""Tests for atlas/intelligence/aggregations/persistence.py.

Integration tests — require ATLAS_INTEGRATION_TESTS=1 and a live DB with
migrations 081-083 applied (atlas_sector_state_v2, atlas_fund_state_v2,
atlas_etf_state_v2 tables present).

Each test cleans up its own rows in teardown so the shared DB stays clean.
The persistence functions use engine.begin() (auto-commit), so we explicitly
DELETE inserted rows after each assertion rather than relying on a SAVEPOINT.

Pattern: insert → assert count == 1 → upsert with changed value → assert
count still == 1 and value is the updated one → DELETE in finally.
"""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import pytest
import sqlalchemy as sa
from sqlalchemy import text

from atlas.intelligence.aggregations.persistence import (
    persist_etf_state_v2,
    persist_fund_state_v2,
    persist_sector_state_v2,
)

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)

# Test sentinel values chosen to not collide with real data
_TEST_SECTOR = "__test_Banking__"
_TEST_MSTAR_ID = "__test_F001__"
_TEST_ETF_TICKER = "__test_NIFTYBEES__"
_TEST_DATE = date(2000, 1, 1)


@_SKIP_INTEGRATION
def test_persist_sector_state_v2_inserts_then_upserts(
    test_engine: sa.Engine,
) -> None:
    """Insert one sector row, then upsert the same (sector, date) with a
    changed dominant_state — must result in exactly 1 row with the new value.
    """
    df = pd.DataFrame(
        [
            {
                "sector": _TEST_SECTOR,
                "date": _TEST_DATE,
                "dominant_state": "stage_2a",
                "dominant_share": 0.70,
                "n_constituents": 10,
                "mean_within_state_rank": 0.65,
                "pct_stage_2": 0.70,
                "pct_stage_3": 0.20,
                "pct_stage_4": 0.10,
                "pct_stage_1": 0.00,
                "pct_uninvestable": 0.00,
            }
        ]
    )
    try:
        n1 = persist_sector_state_v2(test_engine, df)
        assert n1 == 1, f"expected 1 row inserted, got {n1}"

        # Upsert with updated dominant_state — must not duplicate
        df.loc[0, "dominant_state"] = "stage_2b"
        n2 = persist_sector_state_v2(test_engine, df)
        assert n2 == 1, f"expected 1 row upserted, got {n2}"

        with test_engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT dominant_state FROM atlas.atlas_sector_state_v2 "
                    "WHERE sector = :s AND date = :d"
                ),
                {"s": _TEST_SECTOR, "d": _TEST_DATE},
            ).fetchall()
        assert len(rows) == 1, f"expected 1 row total, got {len(rows)}"
        assert (
            rows[0].dominant_state == "stage_2b"
        ), f"expected stage_2b after upsert, got {rows[0].dominant_state}"
    finally:
        with test_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_sector_state_v2 " "WHERE sector = :s AND date = :d"),
                {"s": _TEST_SECTOR, "d": _TEST_DATE},
            )


@_SKIP_INTEGRATION
def test_persist_fund_state_v2_inserts_then_upserts(
    test_engine: sa.Engine,
) -> None:
    """Insert one fund row, then upsert the same (mstar_id, date) with a
    changed composition_state — must result in exactly 1 row with the new value.
    """
    df = pd.DataFrame(
        [
            {
                "mstar_id": _TEST_MSTAR_ID,
                "date": _TEST_DATE,
                "composition_state": "Aligned",
                "holdings_state": "Strong-Holdings",
                "pct_holdings_stage_2": 0.75,
                "pct_holdings_stage_3": 0.15,
                "pct_holdings_stage_4": 0.10,
                "mean_within_state_rank": 0.72,
                "n_holdings": 30,
            }
        ]
    )
    try:
        n1 = persist_fund_state_v2(test_engine, df)
        assert n1 == 1, f"expected 1 row inserted, got {n1}"

        # Upsert with updated composition_state
        df.loc[0, "composition_state"] = "Deteriorating"
        n2 = persist_fund_state_v2(test_engine, df)
        assert n2 == 1, f"expected 1 row upserted, got {n2}"

        with test_engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT composition_state FROM atlas.atlas_fund_state_v2 "
                    "WHERE mstar_id = :m AND date = :d"
                ),
                {"m": _TEST_MSTAR_ID, "d": _TEST_DATE},
            ).fetchall()
        assert len(rows) == 1, f"expected 1 row total, got {len(rows)}"
        assert (
            rows[0].composition_state == "Deteriorating"
        ), f"expected Deteriorating after upsert, got {rows[0].composition_state}"
    finally:
        with test_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_fund_state_v2 " "WHERE mstar_id = :m AND date = :d"),
                {"m": _TEST_MSTAR_ID, "d": _TEST_DATE},
            )


@_SKIP_INTEGRATION
def test_persist_etf_state_v2_inserts_then_upserts(
    test_engine: sa.Engine,
) -> None:
    """Insert one ETF row, then upsert the same (etf_ticker, date) with a
    changed dominant_state — must result in exactly 1 row with the new value.
    """
    df = pd.DataFrame(
        [
            {
                "etf_ticker": _TEST_ETF_TICKER,
                "date": _TEST_DATE,
                "dominant_state": "stage_2a",
                "dominant_share": 0.80,
                "n_holdings": 50,
                "mean_rs_rank_12m": 0.75,
                "pct_stage_2": 0.80,
                "pct_stage_3": 0.10,
                "pct_stage_4": 0.10,
            }
        ]
    )
    try:
        n1 = persist_etf_state_v2(test_engine, df)
        assert n1 == 1, f"expected 1 row inserted, got {n1}"

        # Upsert with updated dominant_state
        df.loc[0, "dominant_state"] = "stage_2b"
        n2 = persist_etf_state_v2(test_engine, df)
        assert n2 == 1, f"expected 1 row upserted, got {n2}"

        with test_engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT dominant_state FROM atlas.atlas_etf_state_v2 "
                    "WHERE etf_ticker = :t AND date = :d"
                ),
                {"t": _TEST_ETF_TICKER, "d": _TEST_DATE},
            ).fetchall()
        assert len(rows) == 1, f"expected 1 row total, got {len(rows)}"
        assert (
            rows[0].dominant_state == "stage_2b"
        ), f"expected stage_2b after upsert, got {rows[0].dominant_state}"
    finally:
        with test_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_etf_state_v2 " "WHERE etf_ticker = :t AND date = :d"),
                {"t": _TEST_ETF_TICKER, "d": _TEST_DATE},
            )


@_SKIP_INTEGRATION
def test_persist_sector_state_v2_returns_zero_for_empty_df(
    test_engine: sa.Engine,
) -> None:
    """Empty DataFrame returns 0 without touching the DB."""
    df = pd.DataFrame(
        columns=[
            "sector",
            "date",
            "dominant_state",
            "dominant_share",
            "n_constituents",
            "mean_within_state_rank",
            "pct_stage_2",
            "pct_stage_3",
            "pct_stage_4",
            "pct_stage_1",
            "pct_uninvestable",
        ]
    )
    result = persist_sector_state_v2(test_engine, df)
    assert result == 0


@_SKIP_INTEGRATION
def test_persist_fund_state_v2_handles_null_mean_within_state_rank(
    test_engine: sa.Engine,
) -> None:
    """None mean_within_state_rank persists as NULL without error."""
    df = pd.DataFrame(
        [
            {
                "mstar_id": _TEST_MSTAR_ID + "_null",
                "date": _TEST_DATE,
                "composition_state": "Mixed",
                "holdings_state": "Unknown",
                "pct_holdings_stage_2": 0.30,
                "pct_holdings_stage_3": 0.40,
                "pct_holdings_stage_4": 0.30,
                "mean_within_state_rank": None,  # NULL — no within_state_rank data
                "n_holdings": 5,
            }
        ]
    )
    try:
        n = persist_fund_state_v2(test_engine, df)
        assert n == 1

        with test_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT mean_within_state_rank FROM atlas.atlas_fund_state_v2 "
                    "WHERE mstar_id = :m AND date = :d"
                ),
                {"m": _TEST_MSTAR_ID + "_null", "d": _TEST_DATE},
            ).first()
        assert row is not None
        assert row.mean_within_state_rank is None
    finally:
        with test_engine.begin() as c:
            c.execute(
                text("DELETE FROM atlas.atlas_fund_state_v2 " "WHERE mstar_id = :m AND date = :d"),
                {"m": _TEST_MSTAR_ID + "_null", "d": _TEST_DATE},
            )
