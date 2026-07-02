"""Tests for atlas_signal_ic persistence."""

from datetime import date

import pytest
from atlas.intelligence.validation.ic_engine import ICResult
from atlas.intelligence.validation.persistence import persist_ic_result
from sqlalchemy import text

from atlas.db import get_engine


@pytest.mark.integration
class TestPersistICResult:
    @pytest.fixture(autouse=True)
    def clean_test_rows(self):
        """Clean up any prior test rows before and after each test."""
        eng = get_engine()
        with eng.connect() as c:
            c.execute(text("DELETE FROM atlas.atlas_signal_ic WHERE signal_name = 'test_signal'"))
            c.commit()
        yield
        with eng.connect() as c:
            c.execute(text("DELETE FROM atlas.atlas_signal_ic WHERE signal_name = 'test_signal'"))
            c.commit()

    def test_inserts_one_row(self):
        eng = get_engine()
        result = ICResult(
            mean_ic=0.067,
            ic_std=0.12,
            ic_t_stat=2.3,
            n_observations=126,
        )
        persist_ic_result(
            engine=eng,
            signal_name="test_signal",
            timeframe="daily",
            forward_period_days=21,
            rolling_window="6M",
            as_of=date(2025, 6, 30),
            result=result,
            quantile_spread_ann=0.085,
            turnover_monthly=0.28,
        )
        with eng.connect() as c:
            row = c.execute(
                text("""
                SELECT signal_name, forward_period_days, mean_ic, ic_t_stat
                FROM atlas.atlas_signal_ic
                WHERE signal_name = 'test_signal'
            """)
            ).fetchone()
        assert row is not None
        assert row[0] == "test_signal"
        assert row[1] == 21
        assert float(row[2]) == pytest.approx(0.067, abs=1e-6)
        assert float(row[3]) == pytest.approx(2.3, abs=1e-4)

    def test_upsert_on_duplicate_key(self):
        """Inserting the same (signal, period, window, as_of) twice updates instead of failing."""
        eng = get_engine()
        result1 = ICResult(mean_ic=0.05, ic_std=0.1, ic_t_stat=2.0, n_observations=100)
        result2 = ICResult(mean_ic=0.08, ic_std=0.12, ic_t_stat=2.5, n_observations=120)

        persist_ic_result(
            engine=eng,
            signal_name="test_signal",
            timeframe="daily",
            forward_period_days=21,
            rolling_window="6M",
            as_of=date(2025, 6, 30),
            result=result1,
            quantile_spread_ann=0.05,
            turnover_monthly=0.30,
        )
        persist_ic_result(
            engine=eng,
            signal_name="test_signal",
            timeframe="daily",
            forward_period_days=21,
            rolling_window="6M",
            as_of=date(2025, 6, 30),
            result=result2,
            quantile_spread_ann=0.09,
            turnover_monthly=0.25,
        )

        with eng.connect() as c:
            row = c.execute(
                text("""
                SELECT mean_ic, n_observations FROM atlas.atlas_signal_ic
                WHERE signal_name='test_signal'
            """)
            ).fetchone()
        # Second call should have overwritten
        assert row is not None
        assert float(row[0]) == pytest.approx(0.08, abs=1e-6)
        assert row[1] == 120
