"""Lens 2 — Sector Composition (M4 Phase B).

Per ``docs/00_METHODOLOGY_LOCK.md`` §12.2 and
``docs/milestones/ATLAS_M4_MUTUAL_FUND_LENSES.md`` §5.

For each fund's monthly holdings disclosure:
- Computes aligned_aum_pct: sum of weights in sectors with state
  ∈ {Overweight, Neutral}
- Computes avoid_aum_pct: sum of weights in sectors with state = Avoid
- Computes sector_concentration: top-3 sector weight
- Classifies composition_state: Aligned / Mixed / Misaligned

Writes to ``atlas.atlas_fund_lens_monthly`` (alongside Lens 3 columns).

Sector state reference uses the most recent atlas_sector_states_daily row
on or before the disclosure date — not today's state. The fund's positioning
at disclosure time is what matters.
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

LENS2_COLUMNS: tuple[str, ...] = (
    "mstar_id",
    "as_of_date",
    "last_disclosed_date",
    "aligned_aum_pct",
    "avoid_aum_pct",
    "sector_concentration",
    "composition_state",
    "compute_run_id",
)

# Minimum AUM coverage required for classification (disclosures < this are
# flagged as unreliable but still written — UI can show a warning).
MIN_COVERAGE_PCT = 0.50


# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #


def load_disclosure_dates(
    engine: Engine,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Return all distinct (mstar_id, as_of_date) disclosure pairs in range."""
    where = ""
    params: dict[str, Any] = {}
    if start_date:
        where += " AND as_of_date >= %(start)s"
        params["start"] = start_date
    if end_date:
        where += " AND as_of_date <= %(end)s"
        params["end"] = end_date

    with open_compute_session(engine) as conn:
        return pd.read_sql(
            f"""
            SELECT mstar_id, MAX(as_of_date) AS as_of_date,
                   MAX(as_of_date) AS last_disclosed_date
            FROM public.de_mf_holdings
            WHERE 1=1 {where}
            GROUP BY mstar_id, as_of_date
            ORDER BY as_of_date, mstar_id
            """,
            conn,
            params=params,
        )


def load_holdings_for_date(
    engine: Engine,
    as_of_date: date,
) -> pd.DataFrame:
    """Load all fund holdings for a single disclosure date."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                h.mstar_id,
                h.as_of_date,
                h.as_of_date AS last_disclosed_date,
                h.instrument_id,
                (h.weight_pct / 100.0) AS weight,
                u.sector
            FROM public.de_mf_holdings h
            LEFT JOIN atlas.atlas_universe_stocks u
                ON u.instrument_id::text = h.instrument_id::text
               AND u.effective_to IS NULL
            WHERE h.as_of_date = %(date)s
            """,
            conn,
            params={"date": as_of_date},
        )
    return df


def load_sector_states_at_date(
    engine: Engine,
    as_of_date: date,
) -> pd.DataFrame:
    """Return the latest sector_state for each sector on or before as_of_date."""
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT DISTINCT ON (sector_name)
                sector_name,
                sector_state
            FROM atlas.atlas_sector_states_daily
            WHERE date <= %(date)s
            ORDER BY sector_name, date DESC
            """,
            conn,
            params={"date": as_of_date},
        )


# --------------------------------------------------------------------------- #
# Computation                                                                  #
# --------------------------------------------------------------------------- #


def compute_lens2_for_date(
    engine: Engine,
    as_of_date: date,
) -> pd.DataFrame:
    """Compute aligned/avoid/concentration metrics for all funds on as_of_date.

    Returns one row per fund that had a holdings disclosure on that date.
    """
    holdings = load_holdings_for_date(engine, as_of_date)
    if holdings.empty:
        return pd.DataFrame()

    sector_states = load_sector_states_at_date(engine, as_of_date)
    state_map = dict(zip(sector_states["sector_name"], sector_states["sector_state"], strict=False))

    holdings["sector_state"] = holdings["sector"].map(state_map)

    results = []
    for mstar_id, grp in holdings.groupby("mstar_id"):
        total_w = grp["weight"].sum()
        last_disc = grp["last_disclosed_date"].max()

        # Sum weights by sector state
        aligned_w = grp.loc[grp["sector_state"].isin(["Overweight", "Neutral"]), "weight"].sum()
        avoid_w = grp.loc[grp["sector_state"] == "Avoid", "weight"].sum()

        # Top-3 sector concentration
        sector_w = grp.dropna(subset=["sector"]).groupby("sector")["weight"].sum().nlargest(3).sum()

        results.append(
            {
                "mstar_id": mstar_id,
                "as_of_date": as_of_date,
                "last_disclosed_date": last_disc,
                "aligned_aum_pct": float(aligned_w) if total_w > 0 else np.nan,
                "avoid_aum_pct": float(avoid_w) if total_w > 0 else np.nan,
                "sector_concentration": float(sector_w) if total_w > 0 else np.nan,
                "_total_weight": float(total_w),
            }
        )

    return pd.DataFrame(results)


# --------------------------------------------------------------------------- #
# Lens 2 classifier                                                            #
# --------------------------------------------------------------------------- #


def classify_composition_state(
    lens2_df: pd.DataFrame,
    thresholds: dict[str, Any],
) -> pd.DataFrame:
    """Three-state composition classification per methodology §12.2.

    Aligned  : aligned_aum_pct >= 70% AND avoid_aum_pct < 10%
    Mixed    : 50-70% aligned OR 10-20% avoid
    Misaligned: < 50% aligned OR >= 20% avoid
    """
    aligned_min = float(thresholds.get("fund_aligned_aum_min_pct", 70)) / 100
    avoid_max = float(thresholds.get("fund_avoid_aum_max_pct", 10)) / 100

    df = lens2_df.copy()
    aligned = df["aligned_aum_pct"].fillna(0)
    avoid = df["avoid_aum_pct"].fillna(0)

    conditions = [
        (aligned < 0.50) | (avoid >= 0.20),  # Misaligned
        (aligned >= aligned_min) & (avoid < avoid_max),  # Aligned
    ]
    choices = ["Misaligned", "Aligned"]
    df["composition_state"] = np.select(conditions, choices, default="Mixed")

    # Rows with insufficient data get None
    low_coverage = df.get("_total_weight", pd.Series(1.0, index=df.index)) < MIN_COVERAGE_PCT
    df.loc[low_coverage, "composition_state"] = None

    return df


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def run_lens2(
    start_date: date | None = None,
    end_date: date | None = None,
    run_id: uuid.UUID | None = None,
    engine: Engine | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute Lens 2 composition metrics for all disclosure dates in range.

    Returns ``{run_id, rows_written, disclosures_processed, errors}``.
    """
    engine = engine or get_engine()
    run_id = run_id or uuid.uuid4()

    if thresholds is None:
        thresholds = load_thresholds("atlas", engine)

    disclosure_dates = load_disclosure_dates(engine, start_date, end_date)
    unique_dates = sorted(disclosure_dates["as_of_date"].unique())

    log.info("lens2_start", disclosure_dates=len(unique_dates))

    total_rows = 0
    errors: list[dict[str, Any]] = []

    for d in unique_dates:
        try:
            df = compute_lens2_for_date(engine, d)
            if df.empty:
                continue
            df = classify_composition_state(df, thresholds)
            df["compute_run_id"] = str(run_id)

            write_cols = [c for c in LENS2_COLUMNS if c in df.columns]
            rows = df_to_pg_rows(df[write_cols])
            n = bulk_upsert(
                engine,
                "atlas.atlas_fund_lens_monthly",
                list(write_cols),
                rows,
                pk_columns=["mstar_id", "as_of_date"],
            )
            total_rows += n
            log.debug("lens2_date_done", date=str(d), rows=n)
        except Exception as exc:
            errors.append({"date": str(d), "error": str(exc)})
            log.error("lens2_date_error", date=str(d), error=str(exc))

    log.info("lens2_complete", rows_written=total_rows, errors=len(errors))
    return {
        "run_id": run_id,
        "rows_written": total_rows,
        "disclosures_processed": len(unique_dates),
        "errors": errors,
    }
