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
