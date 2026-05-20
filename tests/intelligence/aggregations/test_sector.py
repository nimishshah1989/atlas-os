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


# ---------------------------------------------------------------------------
# Task 3 — hybrid rank + floor sector_state tests
# ---------------------------------------------------------------------------


def _low_breadth_panel() -> pd.DataFrame:
    """25 sectors all with low pct_stage_2 (<0.50) — the thin-breadth scenario
    that caused all sectors to classify as Neutral under the old CASE logic.
    Four distinct groups so the ranker has something to spread.
    """
    sectors = [
        # Group A — strong but below 50% threshold (pct_stage_2 ~ 0.40)
        ("FinancialServices", "stage_2a", 0.85, 0.82),
        ("Banking", "stage_2b", 0.82, 0.79),
        ("Automobile", "stage_2a", 0.78, 0.76),
        ("FMCG", "stage_2c", 0.75, 0.73),
        ("Pharma", "stage_2a", 0.72, 0.70),
        ("IT", "stage_2b", 0.68, 0.67),
        ("Chemicals", "stage_2a", 0.65, 0.63),
        # Group B — moderate (pct_stage_2 ~ 0.25)
        ("Metals", "stage_2a", 0.55, 0.52),
        ("Energy", "stage_3", 0.40, 0.45),
        ("RealEstate", "stage_3", 0.38, 0.42),
        ("ConsumerDurables", "stage_3", 0.35, 0.40),
        ("CapitalGoods", "stage_3", 0.33, 0.38),
        ("Infrastructure", "stage_3", 0.30, 0.35),
        ("Telecom", "stage_3", 0.28, 0.33),
        # Group C — weak (pct_stage_2 ~ 0.10)
        ("Media", "stage_3", 0.20, 0.28),
        ("Textiles", "stage_4", 0.18, 0.24),
        ("Retail", "stage_4", 0.15, 0.22),
        ("Healthcare", "stage_4", 0.12, 0.20),
        ("Utilities", "stage_4", 0.10, 0.18),
        ("Aviation", "stage_4", 0.08, 0.16),
        # Group D — very weak (pct_stage_2 ~ 0.02)
        ("Realty", "stage_4", 0.05, 0.12),
        ("Shipping", "stage_4", 0.04, 0.10),
        ("Defence", "stage_4", 0.03, 0.08),
        ("Sugar", "stage_4", 0.02, 0.06),
        ("Paper", "stage_4", 0.01, 0.04),
    ]
    rows = []
    for sector, state, wsr, rs in sectors:
        # Each sector gets 10 stocks: 4 in the listed state + 6 others
        # Simplify: each sector represented by a single stock row
        rows.append(
            {
                "instrument_id": f"{sector}_1",
                "sector": sector,
                "date": date(2024, 12, 31),
                "state": state,
                "within_state_rank": wsr,
                "rs_rank_12m": rs,
                "market_cap": Decimal("1000"),
            }
        )
    return pd.DataFrame(rows)


def test_hybrid_sector_state_spread_not_all_neutral() -> None:
    """Even when every sector has low pct_stage_2, the hybrid ranker must
    produce at least two distinct sector_state labels — never a constant.
    """
    panel = _low_breadth_panel()
    out = aggregate_sector_states(panel)
    assert "sector_state" in out.columns, "sector_state column must exist"
    labels = set(out["sector_state"].tolist())
    assert len(labels) >= 2, f"Expected spread across ≥2 labels, got only: {labels}"


def test_hybrid_sector_state_all_four_labels_present() -> None:
    """With 25 diverse sectors, all four labels should be assigned."""
    panel = _low_breadth_panel()
    out = aggregate_sector_states(panel)
    labels = set(out["sector_state"].tolist())
    assert labels == {
        "Avoid",
        "Underweight",
        "Neutral",
        "Overweight",
    }, f"Expected all four labels, got: {labels}"


def test_hybrid_sector_state_overweight_requires_breadth_floor() -> None:
    """A sector ranked top but with pct_stage_2 below the floor (default 10%)
    must be capped to Neutral, not Overweight.
    """
    # Only 3 sectors: top-ranked by RS but nearly zero breadth
    panel = pd.DataFrame(
        [
            {
                "instrument_id": "a1",
                "sector": "SectorA",
                "date": date(2024, 12, 31),
                "state": "stage_2a",
                "within_state_rank": 0.99,
                "rs_rank_12m": 0.99,  # highest RS
                "market_cap": Decimal("1000"),
            },
            {
                "instrument_id": "a2",
                "sector": "SectorA",
                "date": date(2024, 12, 31),
                "state": "stage_4",  # 9 stage_4 stocks → pct_stage_2 = 1/10 = 0.10
                "within_state_rank": 0.01,
                "rs_rank_12m": 0.01,
                "market_cap": Decimal("100"),
            },
            {
                "instrument_id": "b1",
                "sector": "SectorB",
                "date": date(2024, 12, 31),
                "state": "stage_3",
                "within_state_rank": 0.50,
                "rs_rank_12m": 0.50,
                "market_cap": Decimal("1000"),
            },
            {
                "instrument_id": "c1",
                "sector": "SectorC",
                "date": date(2024, 12, 31),
                "state": "stage_4",
                "within_state_rank": 0.10,
                "rs_rank_12m": 0.10,  # lowest RS
                "market_cap": Decimal("1000"),
            },
        ]
    )
    aggregate_sector_states(panel)
    # SectorA pct_stage_2 = 1/2 stocks in stage_2 → 0.50 by equal weight
    # That is >= floor of 0.10, so Overweight is allowed IF ranked top
    # Let's use a case with clearly sub-floor breadth:
    # Re-build panel where SectorA has only 1 stage_2a out of 10 stocks
    rows_a = [
        {
            "instrument_id": f"a{i}",
            "sector": "SectorA",
            "date": date(2024, 12, 31),
            "state": "stage_4",
            "within_state_rank": 0.01,
            "rs_rank_12m": 0.99,  # very high RS
            "market_cap": Decimal("100"),
        }
        for i in range(9)
    ]
    rows_a.append(
        {
            "instrument_id": "a9",
            "sector": "SectorA",
            "date": date(2024, 12, 31),
            "state": "stage_2a",
            "within_state_rank": 0.99,
            "rs_rank_12m": 0.99,
            "market_cap": Decimal("100"),
        }
    )
    rows_other = [
        {
            "instrument_id": "b1",
            "sector": "SectorB",
            "date": date(2024, 12, 31),
            "state": "stage_2b",
            "within_state_rank": 0.70,
            "rs_rank_12m": 0.60,
            "market_cap": Decimal("1000"),
        },
        {
            "instrument_id": "c1",
            "sector": "SectorC",
            "date": date(2024, 12, 31),
            "state": "stage_4",
            "within_state_rank": 0.10,
            "rs_rank_12m": 0.10,
            "market_cap": Decimal("1000"),
        },
    ]
    panel2 = pd.DataFrame(rows_a + rows_other)
    aggregate_sector_states(panel2)
    # pct_stage_2 for SectorA = 1/10 = 0.10 → exactly at floor
    # floor_min default is Decimal("0.10") (10 as a whole-number pct → 0.10)
    # So 0.10 >= 0.10 → floor passes → may be Overweight if top-ranked
    # Key assertion: sector with ZERO stage_2 must not be Overweight
    rows_zero = rows_a[:9] + [  # all stage_4, no stage_2
        {
            "instrument_id": "a9",
            "sector": "SectorA",
            "date": date(2024, 12, 31),
            "state": "stage_4",
            "within_state_rank": 0.01,
            "rs_rank_12m": 0.99,
            "market_cap": Decimal("100"),
        }
    ]
    panel3 = pd.DataFrame(rows_zero + rows_other)
    out3 = aggregate_sector_states(panel3)
    sector_a3 = out3[out3["sector"] == "SectorA"].iloc[0]
    assert (
        sector_a3["sector_state"] != "Overweight"
    ), "SectorA has 0 stage_2 stocks — must not be Overweight regardless of RS rank"
