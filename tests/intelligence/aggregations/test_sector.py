"""Tests for atlas/intelligence/aggregations/sector.py."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.sector import aggregate_sector_states


def _stock_panel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Banking sector — mostly stage 2
            {
                "instrument_id": "b1",
                "sector": "Banking",
                "date": date(2024, 12, 31),
                "state": "stage_2a",
                "within_state_rank": 0.85,
                "rs_rank_12m": 0.80,
                "market_cap": Decimal("1000"),
            },
            {
                "instrument_id": "b2",
                "sector": "Banking",
                "date": date(2024, 12, 31),
                "state": "stage_2b",
                "within_state_rank": 0.70,
                "rs_rank_12m": 0.75,
                "market_cap": Decimal("500"),
            },
            {
                "instrument_id": "b3",
                "sector": "Banking",
                "date": date(2024, 12, 31),
                "state": "stage_3",
                "within_state_rank": 0.40,
                "rs_rank_12m": 0.40,
                "market_cap": Decimal("200"),
            },
            # IT sector — mostly stage 4
            {
                "instrument_id": "i1",
                "sector": "IT",
                "date": date(2024, 12, 31),
                "state": "stage_4",
                "within_state_rank": None,
                "rs_rank_12m": 0.20,
                "market_cap": Decimal("800"),
            },
            {
                "instrument_id": "i2",
                "sector": "IT",
                "date": date(2024, 12, 31),
                "state": "stage_4",
                "within_state_rank": None,
                "rs_rank_12m": 0.15,
                "market_cap": Decimal("600"),
            },
        ]
    )


def test_aggregate_sector_states_yields_one_row_per_sector_per_date() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    assert len(out) == 2
    assert set(out["sector"].tolist()) == {"Banking", "IT"}


def test_aggregate_sector_states_banking_dominant_state_is_stage_2() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    banking = out[out["sector"] == "Banking"].iloc[0]
    # Banking by market-cap weight: 1000+500=1500 stage_2 vs 200 stage_3.
    assert banking["dominant_state"] in ("stage_2a", "stage_2b")
    assert banking["dominant_share"] == pytest.approx(1500 / 1700, rel=1e-3)


def test_aggregate_sector_states_it_dominant_state_is_stage_4() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    it = out[out["sector"] == "IT"].iloc[0]
    assert it["dominant_state"] == "stage_4"
    assert it["dominant_share"] == pytest.approx(1.0)


def test_aggregate_sector_states_mean_within_state_rank_excludes_nulls() -> None:
    panel = _stock_panel()
    out = aggregate_sector_states(panel)
    banking = out[out["sector"] == "Banking"].iloc[0]
    # Banking constituents within_state_rank: 0.85, 0.70, 0.40 → mean 0.65
    assert banking["mean_within_state_rank"] == pytest.approx(0.65)
    it = out[out["sector"] == "IT"].iloc[0]
    assert it["mean_within_state_rank"] is None or pd.isna(it["mean_within_state_rank"])
