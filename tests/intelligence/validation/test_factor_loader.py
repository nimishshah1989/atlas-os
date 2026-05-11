"""Tests for factor_loader. Uses real DB connection — integration-tier.

Schema notes (verified 2026-05-12):
- atlas_stock_states_daily has 'sector' col (not sector_name) that joins
  directly to atlas_sector_states_daily.sector_name — no universe join needed.
"""

from datetime import date

import pandas as pd
import pytest

from atlas.db import get_engine
from atlas.intelligence.validation.factor_loader import load_decision_state_factor


@pytest.mark.integration
class TestLoadDecisionStateFactor:
    def test_returns_multiindex_dataframe(self) -> None:
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        # MultiIndex (date, instrument_id)
        assert isinstance(df.index, pd.MultiIndex)
        assert df.index.names == ["date", "instrument_id"]
        assert "factor" in df.columns

    def test_factor_in_unit_interval(self) -> None:
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert df["factor"].min() >= 0.0 - 1e-9
        assert df["factor"].max() <= 1.0 + 1e-9
        assert df["factor"].notna().all()  # sentinels already dropped

    def test_empty_range_returns_empty_df(self) -> None:
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(1990, 1, 1),
            end_date=date(1990, 1, 2),
        )
        assert len(df) == 0
        assert "factor" in df.columns

    def test_universe_filter_applies(self) -> None:
        """If a universe_filter is passed, only those instruments appear."""
        eng = get_engine()
        df = load_decision_state_factor(
            engine=eng,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            universe_filter=["00000000-0000-0000-0000-000000000000"],
        )
        assert len(df) == 0
