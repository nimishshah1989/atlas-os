from __future__ import annotations

import pandas as pd


def compute_sector_pivot(signals_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate PPC/NPC counts by sector for one date.

    Input: signals_df with columns: instrument_id, date, is_ppc, is_npc,
           is_tradeable, sector.
    Output: DataFrame with date, sector, ppc_count, npc_count,
            total_tradeable, pivot_balance.
    """
    tradeable = signals_df[signals_df["is_tradeable"].fillna(False)]
    grouped = (
        tradeable.groupby(["date", "sector"])
        .agg(
            ppc_count=("is_ppc", "sum"),
            npc_count=("is_npc", "sum"),
            total_tradeable=("instrument_id", "count"),
        )
        .reset_index()
    )
    grouped["ppc_count"] = grouped["ppc_count"].astype(int)
    grouped["npc_count"] = grouped["npc_count"].astype(int)
    denom = grouped["total_tradeable"].replace(0, pd.NA)
    grouped["pivot_balance"] = (grouped["ppc_count"] - grouped["npc_count"]) / denom
    return grouped
