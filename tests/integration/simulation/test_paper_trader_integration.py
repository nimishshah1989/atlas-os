# tests/integration/simulation/test_paper_trader_integration.py
"""Integration tests for paper_trader — uses transaction-rollback fixture.

These tests hit the real DB (never persist data). They verify:
- MissingAtlasDecisionsError is raised for a future date with no decisions
- fetch_decisions returns a DataFrame with expected columns
- populate_strategy_configs seeded 15 rows

Run: pytest tests/integration/simulation/ -v --tb=short
Requires: real DB connection (run on EC2 or with VPN to Supabase)
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from atlas.simulation.core.paper_trader import (
    MissingAtlasDecisionsError,
    check_decisions_exist,
    fetch_decisions,
)
from atlas.simulation.strategies.loader import populate_strategy_configs

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    return get_engine()


def test_strategy_configs_seeded(engine):
    """populate_strategy_configs() produces 15 rows in the DB."""
    populate_strategy_configs(engine)
    with open_compute_session(engine) as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM atlas.strategy_configs WHERE is_active = TRUE")
        ).scalar()
    assert count == 15, f"Expected 15 strategy configs, got {count}"


def test_fetch_decisions_returns_dataframe(engine):
    """fetch_decisions for a recent date returns a non-empty DataFrame."""
    test_date = date.today() - timedelta(days=30)
    with open_compute_session(engine) as conn:
        df = fetch_decisions(conn, "stocks", test_date)
    if df.empty:
        pytest.skip(f"No stock decisions in DB for {test_date} — run pipeline backfill first")
    assert "instrument_id" in df.columns
    assert "rs_state" in df.columns
    assert "transition_trigger" in df.columns


def test_check_decisions_exist_raises_for_future_date(engine):
    """MissingAtlasDecisionsError raised for a date with no decisions."""
    future_date = date.today() + timedelta(days=365)
    with pytest.raises(MissingAtlasDecisionsError):
        check_decisions_exist(engine, "stocks", future_date)


def test_fetch_decisions_etf_returns_dataframe(engine):
    """fetch_decisions for ETF tier returns a DataFrame."""
    test_date = date.today() - timedelta(days=30)
    with open_compute_session(engine) as conn:
        df = fetch_decisions(conn, "etf", test_date)
    assert "instrument_id" in df.columns
