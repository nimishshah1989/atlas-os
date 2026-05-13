from __future__ import annotations

import pandas as pd

from atlas.compute.cts.sector_pivot import compute_sector_pivot


def _make_signals(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_pivot_balance_computed() -> None:
    """pivot_balance = (ppc - npc) / total_tradeable."""
    df = _make_signals(
        [
            {
                "instrument_id": "A",
                "date": "2024-01-01",
                "sector": "IT",
                "is_tradeable": True,
                "is_ppc": True,
                "is_npc": False,
            },
            {
                "instrument_id": "B",
                "date": "2024-01-01",
                "sector": "IT",
                "is_tradeable": True,
                "is_ppc": False,
                "is_npc": True,
            },
            {
                "instrument_id": "C",
                "date": "2024-01-01",
                "sector": "IT",
                "is_tradeable": True,
                "is_ppc": False,
                "is_npc": False,
            },
        ]
    )
    out = compute_sector_pivot(df)
    row = out[out["sector"] == "IT"].iloc[0]
    assert row["ppc_count"] == 1
    assert row["npc_count"] == 1
    assert row["total_tradeable"] == 3
    assert abs(float(row["pivot_balance"])) < 1e-9  # (1-1)/3 = 0


def test_non_tradeable_excluded() -> None:
    """Non-tradeable rows must not be counted."""
    df = _make_signals(
        [
            {
                "instrument_id": "A",
                "date": "2024-01-01",
                "sector": "BANK",
                "is_tradeable": True,
                "is_ppc": True,
                "is_npc": False,
            },
            {
                "instrument_id": "B",
                "date": "2024-01-01",
                "sector": "BANK",
                "is_tradeable": False,
                "is_ppc": True,
                "is_npc": False,
            },
        ]
    )
    out = compute_sector_pivot(df)
    row = out[out["sector"] == "BANK"].iloc[0]
    assert row["total_tradeable"] == 1
    assert row["ppc_count"] == 1


def test_sector_pivot_stage2_pct():
    """stage2_pct = stage2_count / total_tradeable."""
    df = pd.DataFrame(
        [
            {
                "instrument_id": "A",
                "date": "2024-01-01",
                "sector": "IT",
                "is_tradeable": True,
                "is_ppc": True,
                "is_npc": False,
                "stage": 2,
                "cts_conviction_score": 72.0,
                "cts_action_confidence": True,
            },
            {
                "instrument_id": "B",
                "date": "2024-01-01",
                "sector": "IT",
                "is_tradeable": True,
                "is_ppc": False,
                "is_npc": False,
                "stage": 2,
                "cts_conviction_score": 35.0,
                "cts_action_confidence": False,
            },
            {
                "instrument_id": "C",
                "date": "2024-01-01",
                "sector": "IT",
                "is_tradeable": True,
                "is_ppc": False,
                "is_npc": False,
                "stage": 4,
                "cts_conviction_score": 10.0,
                "cts_action_confidence": False,
            },
        ]
    )
    out = compute_sector_pivot(df)
    row = out[out["sector"] == "IT"].iloc[0]
    assert int(row["stage2_count"]) == 2
    assert abs(float(row["stage2_pct"]) - 2 / 3) < 1e-6
    assert int(row["action_alert_count"]) == 1


def test_sector_pivot_avg_ppc_conviction():
    """avg_ppc_conviction averages conviction of PPC stocks only."""
    df = pd.DataFrame(
        [
            {
                "instrument_id": "A",
                "date": "2024-01-01",
                "sector": "BANK",
                "is_tradeable": True,
                "is_ppc": True,
                "is_npc": False,
                "stage": 2,
                "cts_conviction_score": 70.0,
                "cts_action_confidence": True,
            },
            {
                "instrument_id": "B",
                "date": "2024-01-01",
                "sector": "BANK",
                "is_tradeable": True,
                "is_ppc": True,
                "is_npc": False,
                "stage": 2,
                "cts_conviction_score": 80.0,
                "cts_action_confidence": True,
            },
            {
                "instrument_id": "C",
                "date": "2024-01-01",
                "sector": "BANK",
                "is_tradeable": True,
                "is_ppc": False,
                "is_npc": True,
                "stage": 4,
                "cts_conviction_score": 10.0,
                "cts_action_confidence": False,
            },
        ]
    )
    out = compute_sector_pivot(df)
    row = out[out["sector"] == "BANK"].iloc[0]
    assert abs(float(row["avg_ppc_conviction"]) - 75.0) < 1e-6


def test_sector_pivot_missing_conviction_columns_no_crash():
    """sector_pivot must handle input without cts_conviction_score gracefully."""
    df = pd.DataFrame(
        [
            {
                "instrument_id": "A",
                "date": "2024-01-01",
                "sector": "PHARMA",
                "is_tradeable": True,
                "is_ppc": True,
                "is_npc": False,
            },
            {
                "instrument_id": "B",
                "date": "2024-01-01",
                "sector": "PHARMA",
                "is_tradeable": True,
                "is_ppc": False,
                "is_npc": False,
            },
        ]
    )
    # Should not crash even without stage, cts_conviction_score, cts_action_confidence
    out = compute_sector_pivot(df)
    assert "ppc_count" in out.columns
    assert "stage2_count" in out.columns  # should exist but default to 0
