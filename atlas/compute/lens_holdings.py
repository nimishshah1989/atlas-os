"""Lens 3 — Holdings Quality (M4 Phase C).

Per ``docs/00_METHODOLOGY_LOCK.md`` §12.3 and
``docs/milestones/ATLAS_M4_MUTUAL_FUND_LENSES.md`` §6.

For each fund's monthly holdings disclosure:
- Computes strong_aum_pct: sum of weights in stocks with rs_state ∈
  {Leader, Strong, Emerging}
- Computes weak_aum_pct: sum of weights in stocks with rs_state ∈
  {Weak, Laggard}
- Computes unknown_aum_pct: holdings in stocks outside our 750-stock universe
- Computes holdings_concentration: top-10 holdings weight
- Classifies holdings_state: Strong-Holdings / Decent / Weak-Holdings

Uses stock RS states as of the disclosure date (not today's state).
Funds with unknown_aum_pct > 30% are still classified but flagged.

Writes to ``atlas.atlas_fund_lens_monthly`` (alongside Lens 2 columns).
The bulk_upsert ON CONFLICT DO UPDATE merges Lens 2 + Lens 3 columns
written in the same pipeline run.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

LENS3_COLUMNS: tuple[str, ...] = (
    "mstar_id",
    "as_of_date",
    "last_disclosed_date",
    "strong_aum_pct",
    "weak_aum_pct",
    "unknown_aum_pct",
    "holdings_concentration",
    "holdings_state",
    "compute_run_id",
)

# Funds with unknown_aum_pct above this are flagged in the log.
HIGH_UNKNOWN_THRESHOLD = 0.30


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #


def load_stock_states_at_date(
    engine: Engine,
    as_of_date: date,
    instrument_ids: list[str],
) -> pd.DataFrame:
    """Return the latest rs_state for each instrument_id on or before as_of_date.

    Uses DISTINCT ON to get the most recent row per stock — same pattern as
    atlas_sector_states_daily lookup in Lens 2.
    """
    if not instrument_ids:
        return pd.DataFrame(columns=["instrument_id", "rs_state"])

    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT DISTINCT ON (instrument_id)
                instrument_id::text AS instrument_id,
                rs_state
            FROM atlas.atlas_stock_states_daily
            WHERE instrument_id = ANY(%(ids)s)
              AND date <= %(date)s
            ORDER BY instrument_id, date DESC
            """,
            conn,
            params={"ids": instrument_ids, "date": as_of_date},
        )


# --------------------------------------------------------------------------- #
# Computation                                                                  #
# --------------------------------------------------------------------------- #


def compute_lens3_for_date(
    engine: Engine,
    as_of_date: date,
) -> pd.DataFrame:
    """Compute holdings quality metrics for all funds on as_of_date.

    Returns one row per fund with holdings data on that date.
    """
    # Load holdings
    with open_compute_session(engine) as conn:
        holdings = pd.read_sql(
            """
            SELECT
                h.mstar_id,
                h.as_of_date,
                h.last_disclosed_date,
                h.instrument_id::text AS instrument_id,
                h.weight
            FROM public.de_mf_holdings h
            WHERE h.as_of_date = %(date)s
            """,
            conn,
            params={"date": as_of_date},
        )

    if holdings.empty:
        return pd.DataFrame()

    # Load RS states for all instruments that appear in holdings
    all_ids = holdings["instrument_id"].dropna().unique().tolist()
    stock_states = load_stock_states_at_date(engine, as_of_date, all_ids)
    state_map = dict(zip(stock_states["instrument_id"], stock_states["rs_state"], strict=False))

    holdings["rs_state"] = holdings["instrument_id"].map(state_map)

    # Load universe membership to determine known/unknown stocks
    with open_compute_session(engine) as conn:
        universe_ids_df = pd.read_sql(
            """
            SELECT instrument_id::text AS instrument_id
            FROM atlas.atlas_universe_stocks
            WHERE effective_to IS NULL
            """,
            conn,
        )
    universe_set = set(universe_ids_df["instrument_id"])

    results = []
    for mstar_id, grp in holdings.groupby("mstar_id"):
        total_w = grp["weight"].sum()
        last_disc = grp["last_disclosed_date"].max()

        strong_w = grp.loc[grp["rs_state"].isin(["Leader", "Strong", "Emerging"]), "weight"].sum()
        weak_w = grp.loc[grp["rs_state"].isin(["Weak", "Laggard"]), "weight"].sum()

        # Unknown: instrument_id not in our 750-stock universe
        unknown_w = grp.loc[~grp["instrument_id"].isin(universe_set), "weight"].sum()

        # Top-10 holdings concentration
        top10_w = grp.nlargest(10, "weight")["weight"].sum()

        unknown_pct = float(unknown_w) / float(total_w) if total_w > 0 else np.nan
        if unknown_pct > HIGH_UNKNOWN_THRESHOLD:
            log.warning(
                "lens3_high_unknown",
                mstar_id=mstar_id,
                as_of_date=str(as_of_date),
                unknown_pct=round(unknown_pct, 3),
            )

        results.append(
            {
                "mstar_id": mstar_id,
                "as_of_date": as_of_date,
                "last_disclosed_date": last_disc,
                "strong_aum_pct": float(strong_w) / float(total_w) if total_w > 0 else np.nan,
                "weak_aum_pct": float(weak_w) / float(total_w) if total_w > 0 else np.nan,
                "unknown_aum_pct": unknown_pct,
                "holdings_concentration": float(top10_w) if total_w > 0 else np.nan,
            }
        )

    return pd.DataFrame(results)


# --------------------------------------------------------------------------- #
# Lens 3 classifier                                                            #
# --------------------------------------------------------------------------- #


def classify_holdings_state(
    lens3_df: pd.DataFrame,
    thresholds: dict[str, Any],
) -> pd.DataFrame:
    """Three-state holdings classification per methodology §12.3.

    Strong-Holdings: strong_aum_pct >= 60% AND weak_aum_pct < 15%
    Decent         : strong 40-60% OR weak 15-25%
    Weak-Holdings  : strong < 40% OR weak >= 25%
    """
    strong_min = float(thresholds.get("fund_strong_holdings_min_pct", 60)) / 100
    weak_max = float(thresholds.get("fund_weak_holdings_max_pct", 25)) / 100

    df = lens3_df.copy()
    strong = df["strong_aum_pct"].fillna(0)
    weak = df["weak_aum_pct"].fillna(0)

    conditions = [
        (strong < 0.40) | (weak >= weak_max),  # Weak-Holdings
        (strong >= strong_min) & (weak < 0.15),  # Strong-Holdings
    ]
    choices = ["Weak-Holdings", "Strong-Holdings"]
    df["holdings_state"] = np.select(conditions, choices, default="Decent")

    return df


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def run_lens3(
    start_date: date | None = None,
    end_date: date | None = None,
    run_id: uuid.UUID | None = None,
    engine: Engine | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute Lens 3 holdings quality for all disclosure dates in range.

    Returns ``{run_id, rows_written, disclosures_processed, errors}``.
    """
    engine = engine or get_engine()
    run_id = run_id or uuid.uuid4()

    if thresholds is None:
        thresholds = load_thresholds(engine)

    with open_compute_session(engine) as conn:
        disclosure_dates_df = pd.read_sql(
            """
            SELECT DISTINCT as_of_date
            FROM public.de_mf_holdings
            WHERE (%s IS NULL OR as_of_date >= %s)
              AND (%s IS NULL OR as_of_date <= %s)
            ORDER BY as_of_date
            """,
            conn,
            params=[start_date, start_date, end_date, end_date],
        )
    unique_dates = sorted(disclosure_dates_df["as_of_date"].tolist())

    log.info("lens3_start", disclosure_dates=len(unique_dates))

    total_rows = 0
    errors: list[dict[str, Any]] = []

    for d in unique_dates:
        try:
            df = compute_lens3_for_date(engine, d)
            if df.empty:
                continue
            df = classify_holdings_state(df, thresholds)
            df["compute_run_id"] = str(run_id)

            write_cols = [c for c in LENS3_COLUMNS if c in df.columns]
            rows = df_to_pg_rows(df[write_cols])
            n = bulk_upsert(
                engine,
                "atlas.atlas_fund_lens_monthly",
                list(write_cols),
                rows,
                pk_columns=["mstar_id", "as_of_date"],
            )
            total_rows += n
        except Exception as exc:
            errors.append({"date": str(d), "error": str(exc)})
            log.error("lens3_date_error", date=str(d), error=str(exc))

    log.info("lens3_complete", rows_written=total_rows, errors=len(errors))
    return {
        "run_id": run_id,
        "rows_written": total_rows,
        "disclosures_processed": len(unique_dates),
        "errors": errors,
    }
