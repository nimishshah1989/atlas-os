"""Tests for atlas/intelligence/aggregations/etf.py.

Panel shape post-rewrite: one row per (etf_ticker, date) from
atlas_etf_states_daily. Columns: etf_ticker, date, rs_state,
momentum_state.
"""

from datetime import date

import pandas as pd
import pytest

from atlas.intelligence.aggregations.etf import (
    _map_etf_to_weinstein,
    aggregate_etf_states,
)


def _etf_panel() -> pd.DataFrame:
    """Synthetic atlas_etf_states_daily panel for tests."""
    return pd.DataFrame(
        [
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2024, 12, 31),
                "rs_state": "Strong",
                "momentum_state": "Improving",
            },
            {
                "etf_ticker": "BANKBEES",
                "date": date(2024, 12, 31),
                "rs_state": "Average",
                "momentum_state": "Deteriorating",
            },
            {
                "etf_ticker": "JUNIORBEES",
                "date": date(2024, 12, 31),
                "rs_state": "Weak",
                "momentum_state": "Collapsing",
            },
        ]
    )


# --- _map_etf_to_weinstein unit tests ---


def test_map_etf_leader_improving_is_stage_2a() -> None:
    assert _map_etf_to_weinstein("Leader", "Improving") == "stage_2a"


def test_map_etf_leader_flat_is_stage_2a() -> None:
    assert _map_etf_to_weinstein("Leader", "Flat") == "stage_2a"


def test_map_etf_strong_improving_is_stage_2a() -> None:
    assert _map_etf_to_weinstein("Strong", "Improving") == "stage_2a"


def test_map_etf_strong_flat_is_stage_2b() -> None:
    assert _map_etf_to_weinstein("Strong", "Flat") == "stage_2b"


def test_map_etf_average_improving_is_stage_2c() -> None:
    assert _map_etf_to_weinstein("Average", "Improving") == "stage_2c"


def test_map_etf_average_deteriorating_is_stage_3() -> None:
    assert _map_etf_to_weinstein("Average", "Deteriorating") == "stage_3"


def test_map_etf_weak_collapsing_is_stage_4() -> None:
    assert _map_etf_to_weinstein("Weak", "Collapsing") == "stage_4"


def test_map_etf_illiquid_is_uninvestable() -> None:
    assert _map_etf_to_weinstein("ILLIQUID", "ILLIQUID") == "uninvestable"


def test_map_etf_insufficient_history_is_uninvestable() -> None:
    assert _map_etf_to_weinstein("INSUFFICIENT_HISTORY", "INSUFFICIENT_HISTORY") == "uninvestable"


# --- aggregate_etf_states tests ---


def test_aggregate_etf_states_one_row_per_etf() -> None:
    out = aggregate_etf_states(_etf_panel())
    assert len(out) == 3
    assert set(out["etf_ticker"]) == {"NIFTYBEES", "BANKBEES", "JUNIORBEES"}


def test_aggregate_etf_states_niftybees_stage_2() -> None:
    out = aggregate_etf_states(_etf_panel())
    n = out[out["etf_ticker"] == "NIFTYBEES"].iloc[0]
    # Strong + Improving -> stage_2a
    assert n["dominant_state"] == "stage_2a"
    assert n["pct_stage_2"] == pytest.approx(1.0)
    assert n["pct_stage_3"] == pytest.approx(0.0)
    assert n["pct_stage_4"] == pytest.approx(0.0)


def test_aggregate_etf_states_bankbees_stage_3() -> None:
    out = aggregate_etf_states(_etf_panel())
    b = out[out["etf_ticker"] == "BANKBEES"].iloc[0]
    # Average + Deteriorating -> stage_3
    assert b["dominant_state"] == "stage_3"
    assert b["pct_stage_3"] == pytest.approx(1.0)


def test_aggregate_etf_states_juniorbees_stage_4() -> None:
    out = aggregate_etf_states(_etf_panel())
    j = out[out["etf_ticker"] == "JUNIORBEES"].iloc[0]
    # Weak + Collapsing -> stage_4
    assert j["dominant_state"] == "stage_4"
    assert j["pct_stage_4"] == pytest.approx(1.0)


def test_aggregate_etf_states_niftybees_mean_rs_rank() -> None:
    out = aggregate_etf_states(_etf_panel())
    n = out[out["etf_ticker"] == "NIFTYBEES"].iloc[0]
    # Strong -> implied rank 0.80
    assert n["mean_rs_rank_12m"] == pytest.approx(0.80)


def test_aggregate_etf_states_empty_returns_schema() -> None:
    out = aggregate_etf_states(pd.DataFrame())
    assert list(out.columns) == [
        "etf_ticker",
        "date",
        "dominant_state",
        "dominant_share",
        "n_holdings",
        "mean_rs_rank_12m",
        "pct_stage_2",
        "pct_stage_3",
        "pct_stage_4",
    ]
    assert len(out) == 0


def test_aggregate_etf_states_n_holdings_is_one_per_etf() -> None:
    """Each ETF row in the panel is treated as a single self-constituent."""
    out = aggregate_etf_states(_etf_panel())
    assert (out["n_holdings"] == 1).all()
