"""Unit tests for compute_rs_velocity in atlas/compute/sectors.py.

Tests are pure pandas — no DB. Each test verifies a specific invariant of
the velocity formula to catch regression if the formula changes.
"""

import pandas as pd

# Import the function under test. Will FAIL until the function is added to
# sectors.py — that's the expected TDD red state.
from atlas.compute.sectors import compute_rs_velocity


def _make_metrics(sector: str, dates_rs: list[tuple[str, float | None]]) -> pd.DataFrame:
    """Build a minimal metrics DataFrame for one sector.

    ``dates_rs``: list of ``(date_str, rs_value | None)``.
    """
    rows = [
        {
            "sector_name": sector,
            "date": pd.Timestamp(d),
            "bottomup_rs_3m_nifty500": rs,
        }
        for d, rs in dates_rs
    ]
    return pd.DataFrame(rows)


class TestComputeRsVelocity:
    def test_velocity_is_rate_of_change(self) -> None:
        """28 days apart: velocity = (new - old) / abs(old)."""
        df = _make_metrics(
            "IT",
            [
                ("2026-01-01", 1.10),
                ("2026-01-29", 1.21),  # 28 calendar days later
            ],
        )
        result = compute_rs_velocity(df, window_days=28)
        row = result.loc[result["date"] == pd.Timestamp("2026-01-29"), "rs_velocity"]
        assert not row.empty
        assert abs(float(row.iloc[0]) - 0.1) < 1e-6

    def test_velocity_is_null_if_no_prior_window(self) -> None:
        """First date(s) with no prior window → rs_velocity is NaN/None."""
        df = _make_metrics(
            "IT",
            [
                ("2026-01-01", 1.10),
                ("2026-01-05", 1.15),
            ],
        )
        result = compute_rs_velocity(df, window_days=28)
        # Both dates are less than 28 days apart → both should be NaN
        assert result["rs_velocity"].isna().all()

    def test_zero_rs_base_produces_null(self) -> None:
        """Zero denominator must produce NULL, not inf or NaN from division."""
        df = _make_metrics(
            "Banking",
            [
                ("2026-01-01", 0.0),
                ("2026-01-29", 0.5),
            ],
        )
        result = compute_rs_velocity(df, window_days=28)
        row = result.loc[result["date"] == pd.Timestamp("2026-01-29"), "rs_velocity"]
        # Zero base → velocity should be NaN (guarded division)
        assert row.empty or pd.isna(row.iloc[0])

    def test_multiple_sectors_computed_independently(self) -> None:
        """Each sector's velocity must use only its own prior RS value."""
        it_df = _make_metrics("IT", [("2026-01-01", 1.0), ("2026-01-29", 1.1)])
        bank_df = _make_metrics("Banking", [("2026-01-01", 2.0), ("2026-01-29", 2.2)])
        df = pd.concat([it_df, bank_df], ignore_index=True)
        result = compute_rs_velocity(df, window_days=28)

        it_vel = result.loc[
            (result["sector_name"] == "IT") & (result["date"] == pd.Timestamp("2026-01-29")),
            "rs_velocity",
        ].iloc[0]
        bank_vel = result.loc[
            (result["sector_name"] == "Banking") & (result["date"] == pd.Timestamp("2026-01-29")),
            "rs_velocity",
        ].iloc[0]

        assert abs(float(it_vel) - 0.1) < 1e-6
        assert abs(float(bank_vel) - 0.1) < 1e-6

    def test_rs_velocity_column_added_to_output(self) -> None:
        """Output DataFrame must have rs_velocity column even if all NaN."""
        df = _make_metrics("IT", [("2026-01-01", 1.10)])
        result = compute_rs_velocity(df, window_days=28)
        assert "rs_velocity" in result.columns

    def test_negative_velocity_on_falling_rs(self) -> None:
        """RS declining → negative velocity."""
        df = _make_metrics(
            "FMCG",
            [
                ("2026-01-01", 1.20),
                ("2026-01-29", 1.08),  # RS fell
            ],
        )
        result = compute_rs_velocity(df, window_days=28)
        row = result.loc[result["date"] == pd.Timestamp("2026-01-29"), "rs_velocity"]
        assert float(row.iloc[0]) < 0
