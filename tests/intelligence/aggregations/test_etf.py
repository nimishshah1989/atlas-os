"""Tests for atlas/intelligence/aggregations/etf.py."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from atlas.intelligence.aggregations.etf import aggregate_etf_states


def _etf_holdings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2024, 12, 31),
                "instrument_id": "a",
                "weight_pct": Decimal("60"),
                "state": "stage_2a",
                "rs_rank_12m": 0.80,
            },
            {
                "etf_ticker": "NIFTYBEES",
                "date": date(2024, 12, 31),
                "instrument_id": "b",
                "weight_pct": Decimal("40"),
                "state": "stage_2b",
                "rs_rank_12m": 0.75,
            },
            {
                "etf_ticker": "BANKBEES",
                "date": date(2024, 12, 31),
                "instrument_id": "c",
                "weight_pct": Decimal("100"),
                "state": "stage_3",
                "rs_rank_12m": 0.40,
            },
        ]
    )


def test_aggregate_etf_states_one_row_per_etf() -> None:
    out = aggregate_etf_states(_etf_holdings())
    assert len(out) == 2


def test_aggregate_etf_states_niftybees_stage_2_dominant() -> None:
    out = aggregate_etf_states(_etf_holdings())
    n = out[out["etf_ticker"] == "NIFTYBEES"].iloc[0]
    assert n["dominant_state"] in ("stage_2a", "stage_2b")
    assert n["mean_rs_rank_12m"] == pytest.approx(0.60 * 0.80 + 0.40 * 0.75)
