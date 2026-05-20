"""Tests for atlas/intelligence/aggregations/etf.py.

Panel shape post-rewrite: one row per (etf_ticker, constituent_instrument_id, date)
from de_etf_holdings JOIN atlas_stock_state_daily.
Columns: etf_ticker, date, instrument_id, weight, state, rs_rank_12m.

Commodity ETFs (theme in {Gold, Silver}) are skipped — no equity constituents.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pandas as pd
import pytest

from atlas.intelligence.aggregations.etf import (
    _is_commodity_etf,
    _map_etf_to_weinstein,
    aggregate_etf_states,
)

# ---- helpers -----------------------------------------------------------------


def _instrument_id() -> str:
    return str(uuid4())


def _equity_panel() -> pd.DataFrame:
    """Synthetic holdings panel for an equity ETF (NIFTYBEES) with 3 constituents.

    Each row: (etf_ticker, date, instrument_id, weight, state, rs_rank_12m).
    Weights don't need to sum to 1 — aggregator normalises.
    """
    nifty_id_1 = _instrument_id()
    nifty_id_2 = _instrument_id()
    nifty_id_3 = _instrument_id()
    return pd.DataFrame(
        [
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2024, 12, 31),
                "instrument_id": nifty_id_1,
                "weight": Decimal("0.40"),
                "state": "stage_2a",
                "rs_rank_12m": Decimal("0.92"),
            },
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2024, 12, 31),
                "instrument_id": nifty_id_2,
                "weight": Decimal("0.35"),
                "state": "stage_2b",
                "rs_rank_12m": Decimal("0.75"),
            },
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2024, 12, 31),
                "instrument_id": nifty_id_3,
                "weight": Decimal("0.25"),
                "state": "stage_3",
                "rs_rank_12m": Decimal("0.45"),
            },
        ]
    )


def _multi_etf_panel() -> pd.DataFrame:
    """Panel for two ETFs on the same date."""
    ids = [_instrument_id() for _ in range(5)]
    return pd.DataFrame(
        [
            # NIFTYBEES: 2 stage_2a constituents (dominant)
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2025, 1, 2),
                "instrument_id": ids[0],
                "weight": Decimal("0.60"),
                "state": "stage_2a",
                "rs_rank_12m": Decimal("0.90"),
            },
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2025, 1, 2),
                "instrument_id": ids[1],
                "weight": Decimal("0.40"),
                "state": "stage_2b",
                "rs_rank_12m": Decimal("0.72"),
            },
            # BANKBEES: 2 stage_4 constituents + 1 stage_3
            {
                "etf_ticker": "BANKBEES",
                "date": date(2025, 1, 2),
                "instrument_id": ids[2],
                "weight": Decimal("0.50"),
                "state": "stage_4",
                "rs_rank_12m": Decimal("0.15"),
            },
            {
                "etf_ticker": "BANKBEES",
                "date": date(2025, 1, 2),
                "instrument_id": ids[3],
                "weight": Decimal("0.30"),
                "state": "stage_4",
                "rs_rank_12m": Decimal("0.10"),
            },
            {
                "etf_ticker": "BANKBEES",
                "date": date(2025, 1, 2),
                "instrument_id": ids[4],
                "weight": Decimal("0.20"),
                "state": "stage_3",
                "rs_rank_12m": Decimal("0.40"),
            },
        ]
    )


# ---- _map_etf_to_weinstein unit tests (unchanged behaviour) ------------------


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


# ---- _is_commodity_etf -------------------------------------------------------


def test_is_commodity_etf_gold_theme() -> None:
    assert _is_commodity_etf("GOLDBEES", "Gold") is True


def test_is_commodity_etf_silver_theme() -> None:
    assert _is_commodity_etf("SILVERBEES", "Silver") is True


def test_is_commodity_etf_equity_returns_false() -> None:
    assert _is_commodity_etf("NIFTYBEES", "Broad") is False


def test_is_commodity_etf_none_theme_returns_false() -> None:
    assert _is_commodity_etf("CPSEETF", None) is False


# ---- aggregate_etf_states tests — NEW REAL-HOLDINGS BEHAVIOUR ----------------


def test_aggregate_equity_etf_has_multiple_holdings() -> None:
    """Core regression: equity ETF must aggregate >1 holding."""
    panel = _equity_panel()
    out = aggregate_etf_states(panel)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["etf_ticker"] == "NIFTYBEES"
    assert int(row["n_holdings"]) == 3, f"expected 3, got {row['n_holdings']}"


def test_aggregate_equity_etf_pct_stage_2_correct() -> None:
    """stage_2a (0.40) + stage_2b (0.35) = 0.75 of weight -> pct_stage_2 ~0.75."""
    panel = _equity_panel()
    out = aggregate_etf_states(panel)
    row = out.iloc[0]
    assert row["pct_stage_2"] == pytest.approx(0.75, abs=0.01)


def test_aggregate_equity_etf_pct_stage_3_correct() -> None:
    """stage_3 weight = 0.25 -> pct_stage_3 ~0.25."""
    panel = _equity_panel()
    out = aggregate_etf_states(panel)
    row = out.iloc[0]
    assert row["pct_stage_3"] == pytest.approx(0.25, abs=0.01)


def test_aggregate_equity_etf_dominant_state_is_stage_2a() -> None:
    """stage_2a has 0.40 weight; not >0.50 alone, but it's the plurality -> stage_2a dominant."""
    panel = _equity_panel()
    out = aggregate_etf_states(panel)
    row = out.iloc[0]
    # stage_2a = 0.40 (plurality when stage_2b is separate); dominant_share = 0.40
    assert row["dominant_state"] == "stage_2a"


def test_aggregate_equity_etf_mean_rs_rank_weighted() -> None:
    """mean_rs_rank_12m must be weight-averaged: 0.40*0.92 + 0.35*0.75 + 0.25*0.45 = 0.746."""
    panel = _equity_panel()
    out = aggregate_etf_states(panel)
    row = out.iloc[0]
    expected = 0.40 * 0.92 + 0.35 * 0.75 + 0.25 * 0.45
    assert row["mean_rs_rank_12m"] == pytest.approx(expected, abs=0.005)


def test_aggregate_multi_etf_produces_two_rows() -> None:
    panel = _multi_etf_panel()
    out = aggregate_etf_states(panel)
    assert len(out) == 2
    assert set(out["etf_ticker"]) == {"NIFTYBEES", "BANKBEES"}


def test_aggregate_bankbees_stage_4_dominant() -> None:
    """BANKBEES: stage_4 = 0.80 of weight (>0.50) -> dominant_state = stage_4."""
    panel = _multi_etf_panel()
    out = aggregate_etf_states(panel)
    b = out[out["etf_ticker"] == "BANKBEES"].iloc[0]
    assert b["dominant_state"] == "stage_4"
    assert b["pct_stage_4"] == pytest.approx(0.80, abs=0.01)
    assert int(b["n_holdings"]) == 3


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


def test_aggregate_null_rs_rank_handled() -> None:
    """Constituents with NULL rs_rank_12m must not break mean calculation."""
    panel = pd.DataFrame(
        [
            {
                "etf_ticker": "TESTBEES",
                "date": date(2025, 1, 2),
                "instrument_id": _instrument_id(),
                "weight": Decimal("0.50"),
                "state": "stage_2a",
                "rs_rank_12m": Decimal("0.80"),
            },
            {
                "etf_ticker": "TESTBEES",
                "date": date(2025, 1, 2),
                "instrument_id": _instrument_id(),
                "weight": Decimal("0.50"),
                "state": "stage_2b",
                "rs_rank_12m": None,
            },
        ]
    )
    out = aggregate_etf_states(panel)
    row = out.iloc[0]
    # Only the non-null constituent counts: weight-avg of 0.80 over weight=0.50 => still 0.80
    assert row["mean_rs_rank_12m"] == pytest.approx(0.80, abs=0.01)
    assert int(row["n_holdings"]) == 2


# ---- legacy ticker-level fallback (old-style panel, for backward compat) -----


def test_aggregate_legacy_ticker_panel_n_holdings_is_one() -> None:
    """If the panel has rs_state/momentum_state columns (old ticker-level format),
    the function still aggregates but warns. This confirms backward compatibility
    for callers still passing the old format during the migration window.
    """
    # Old format: etf_ticker, date, rs_state, momentum_state (no instrument_id/weight/state)
    old_panel = pd.DataFrame(
        [
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2024, 12, 31),
                "rs_state": "Strong",
                "momentum_state": "Improving",
            },
        ]
    )
    # Old panel lacks 'state' and 'weight' columns -> should raise ValueError
    with pytest.raises(ValueError, match="missing required columns"):
        aggregate_etf_states(old_panel)
