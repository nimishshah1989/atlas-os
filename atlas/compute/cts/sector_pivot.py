from __future__ import annotations

from typing import cast

import pandas as pd


def compute_sector_pivot(signals_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate PPC/NPC counts and conviction metrics by sector per date.

    Required input columns: instrument_id, date, is_ppc, is_npc, is_tradeable, sector
    Optional (graceful if missing): stage, cts_conviction_score, cts_action_confidence

    Output columns:
        date, sector, ppc_count, npc_count, total_tradeable, pivot_balance,
        stage2_count, stage2_pct, avg_ppc_conviction, action_alert_count
    """
    tradeable = signals_df[signals_df["is_tradeable"].fillna(False)].copy()

    # Determine which optional columns are present
    has_stage = "stage" in tradeable.columns
    has_conviction = "cts_conviction_score" in tradeable.columns
    has_action = "cts_action_confidence" in tradeable.columns

    agg_spec: dict = {
        "ppc_count": ("is_ppc", "sum"),
        "npc_count": ("is_npc", "sum"),
        "total_tradeable": ("instrument_id", "count"),
    }

    if has_stage:
        agg_spec["stage2_count"] = ("stage", lambda s: (s == 2).sum())
    if has_action:
        agg_spec["action_alert_count"] = (
            "cts_action_confidence",
            lambda s: s.fillna(False).sum(),
        )

    grouped = tradeable.groupby(["date", "sector"]).agg(**agg_spec).reset_index()
    grouped["ppc_count"] = grouped["ppc_count"].astype(int)
    grouped["npc_count"] = grouped["npc_count"].astype(int)

    if "stage2_count" not in grouped.columns:
        grouped["stage2_count"] = 0
    else:
        grouped["stage2_count"] = grouped["stage2_count"].astype(int)

    if "action_alert_count" not in grouped.columns:
        grouped["action_alert_count"] = 0
    else:
        grouped["action_alert_count"] = grouped["action_alert_count"].astype(int)

    denom = grouped["total_tradeable"].replace(0, pd.NA)
    grouped["pivot_balance"] = (grouped["ppc_count"] - grouped["npc_count"]) / denom
    grouped["stage2_pct"] = grouped["stage2_count"] / denom

    # avg_ppc_conviction: mean of cts_conviction_score for PPC stocks only
    if has_conviction:
        ppc_mask: pd.Series = tradeable["is_ppc"].fillna(False).astype(bool)  # type: ignore[assignment]
        ppc_only: pd.DataFrame = cast(pd.DataFrame, tradeable[ppc_mask])
        if not ppc_only.empty:
            avg_conv = (
                ppc_only.groupby(["date", "sector"])["cts_conviction_score"]
                .mean()
                .reset_index()
                .rename(columns={"cts_conviction_score": "avg_ppc_conviction"})
            )
            grouped = grouped.merge(avg_conv, on=["date", "sector"], how="left")
        else:
            grouped["avg_ppc_conviction"] = pd.NA
    else:
        grouped["avg_ppc_conviction"] = pd.NA

    return grouped
