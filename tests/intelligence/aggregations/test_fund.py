"""Tests for atlas/intelligence/aggregations/fund.py."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.fund import (
    aggregate_fund_composition,
    derive_fund_recommendation,
)


def _holdings_panel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "mstar_id": "F1",
                "date": date(2024, 12, 31),
                "instrument_id": "a",
                "weight_pct": Decimal("40"),
                "state": "stage_2a",
                "within_state_rank": 0.80,
            },
            {
                "mstar_id": "F1",
                "date": date(2024, 12, 31),
                "instrument_id": "b",
                "weight_pct": Decimal("35"),
                "state": "stage_2b",
                "within_state_rank": 0.70,
            },
            {
                "mstar_id": "F1",
                "date": date(2024, 12, 31),
                "instrument_id": "c",
                "weight_pct": Decimal("25"),
                "state": "stage_4",
                "within_state_rank": None,
            },
            {
                "mstar_id": "F2",
                "date": date(2024, 12, 31),
                "instrument_id": "d",
                "weight_pct": Decimal("60"),
                "state": "stage_4",
                "within_state_rank": None,
            },
            {
                "mstar_id": "F2",
                "date": date(2024, 12, 31),
                "instrument_id": "e",
                "weight_pct": Decimal("40"),
                "state": "stage_3",
                "within_state_rank": 0.30,
            },
        ]
    )


def test_aggregate_fund_composition_yields_one_row_per_fund() -> None:
    out = aggregate_fund_composition(_holdings_panel())
    assert len(out) == 2
    assert set(out["mstar_id"]) == {"F1", "F2"}


def test_aggregate_fund_composition_f1_aligned_to_stage_2() -> None:
    out = aggregate_fund_composition(_holdings_panel())
    f1 = out[out["mstar_id"] == "F1"].iloc[0]
    # 40% stage_2a + 35% stage_2b = 75% in stage 2 → composition_state='Aligned'
    assert f1["composition_state"] == "Aligned"
    assert f1["pct_holdings_stage_2"] == pytest.approx(0.75)


def test_aggregate_fund_composition_f2_deteriorating() -> None:
    out = aggregate_fund_composition(_holdings_panel())
    f2 = out[out["mstar_id"] == "F2"].iloc[0]
    # 100% stage_3/4 → composition_state='Deteriorating'
    assert f2["composition_state"] == "Deteriorating"


def test_derive_fund_recommendation_aligned_strong_holdings_recommends() -> None:
    rec = derive_fund_recommendation(
        nav_state="Leader NAV",
        composition_state="Aligned",
        holdings_state="Strong-Holdings",
    )
    assert rec == "Recommended"


def test_derive_fund_recommendation_deteriorating_recommends_avoid() -> None:
    rec = derive_fund_recommendation(
        nav_state="Weak NAV",
        composition_state="Deteriorating",
        holdings_state="Weak-Holdings",
    )
    assert rec == "Avoid"
