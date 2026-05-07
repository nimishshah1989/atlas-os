"""Fund decision pipeline — M5 Phase F.

Per ``docs/00_METHODOLOGY_LOCK.md`` §13.6 and
``docs/milestones/ATLAS_M5_DECISION_ENGINE.md`` §9.

Computes for each (fund, date):
  - fund_recommendation: Recommended / Hold / Reduce / Exit
  - is_investable: True when recommendation is Recommended
  - Gate columns: performance_gate, sectors_gate, stocks_gate, market_gate
  - Four lens-level exit triggers
  - Four recommendation-level transition triggers
  - weeks_in_current_state
  - last_week_recommendation

Writes to ``atlas.atlas_fund_decisions_daily``.

Fund decisions use the three-tuple state (nav_state, composition_state,
holdings_state) from M4 plus market regime. The recommendation reflects
whether the fund is suitable for new money now, not just whether it is
performing well historically.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.config import Config
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

DECISIONS_COLUMNS: tuple[str, ...] = (
    "mstar_id",
    "date",
    "recommendation",
    "is_investable",
    "performance_gate",
    "sectors_gate",
    "stocks_gate",
    "market_gate",
    "exit_market_riskoff",
    "exit_composition_misaligned",
    "exit_holdings_weak",
    "exit_nav_deteriorate",
    "entry_trigger",
    "exit_trigger",
    "reduce_trigger",
    "add_trigger",
    "last_week_recommendation",
    "weeks_in_current_state",
    "compute_run_id",
)

NAV_STRONG_STATES = frozenset(["Leader NAV", "Strong NAV"])
NAV_POSITIVE_STATES = frozenset(["Leader NAV", "Strong NAV", "Average NAV", "Emerging NAV"])

RECOMMENDATION_RANK = {"Recommended": 4, "Hold": 3, "Reduce": 2, "Exit": 1}

# Upgrade transitions that fire add_trigger
_UPGRADE_PAIRS = frozenset(
    {
        ("Hold", "Recommended"),
        ("Reduce", "Recommended"),
        ("Reduce", "Hold"),
        ("Exit", "Reduce"),
        ("Exit", "Hold"),
        ("Exit", "Recommended"),
    }
)


# --------------------------------------------------------------------------- #
# Core loader                                                                  #
# --------------------------------------------------------------------------- #


def _load_fund_states_with_regime(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT
                fs.mstar_id,
                fs.date,
                fs.nav_state,
                fs.composition_state,
                fs.holdings_state,
                mr.regime_state,
                mr.dislocation_active
            FROM atlas.atlas_fund_states_daily fs
            LEFT JOIN atlas.atlas_market_regime_daily mr ON mr.date = fs.date
            WHERE fs.date BETWEEN %(start)s AND %(end)s
              AND fs.nav_state IS NOT NULL
              AND fs.nav_state != 'DISLOCATION_SUSPENDED'
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# --------------------------------------------------------------------------- #
# Recommendation logic                                                         #
# --------------------------------------------------------------------------- #


def compute_fund_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """Apply fund recommendation taxonomy per methodology §13.6."""

    def _recommend(row: Any) -> str:
        if row.get("dislocation_active"):
            return "Exit"
        if row["regime_state"] == "Risk-Off":
            return "Exit"
        if row["nav_state"] == "Laggard NAV":
            return "Exit"
        if row["nav_state"] == "Weak NAV":
            return "Reduce"
        if row["composition_state"] == "Misaligned" and row["holdings_state"] == "Weak-Holdings":
            return "Reduce"
        if (
            row["nav_state"] in NAV_STRONG_STATES
            and row["composition_state"] == "Aligned"
            and row["holdings_state"] == "Strong-Holdings"
        ):
            return "Recommended"
        return "Hold"

    df["recommendation"] = df.apply(_recommend, axis=1)
    df["is_investable"] = df["recommendation"] == "Recommended"

    # Gate breakdown (for UI transparency)
    df["performance_gate"] = df["nav_state"].isin(NAV_STRONG_STATES)
    df["sectors_gate"] = df["composition_state"] != "Misaligned"
    df["stocks_gate"] = df["holdings_state"] != "Weak-Holdings"
    df["market_gate"] = (df["regime_state"] != "Risk-Off") & ~df["dislocation_active"].fillna(False)

    return df


# --------------------------------------------------------------------------- #
# Lens-level exit triggers                                                     #
# --------------------------------------------------------------------------- #


def compute_fund_exit_triggers(df: pd.DataFrame) -> pd.DataFrame:
    """Four lens-level exit triggers per methodology §13.6."""
    df["exit_market_riskoff"] = df["regime_state"] == "Risk-Off"
    df["exit_composition_misaligned"] = df["composition_state"] == "Misaligned"
    df["exit_holdings_weak"] = df["holdings_state"] == "Weak-Holdings"
    df["exit_nav_deteriorate"] = df["nav_state"].isin(["Weak NAV", "Laggard NAV"])
    return df


# --------------------------------------------------------------------------- #
# Recommendation transition triggers                                          #
# --------------------------------------------------------------------------- #


def compute_recommendation_transitions(
    df: pd.DataFrame,
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Add entry_trigger, exit_trigger, reduce_trigger, add_trigger.

    Compares each (fund, date) recommendation to the most recent prior
    recommendation. The 'prior' is the last row in atlas_fund_decisions_daily
    with date < today (already written rows).

    For backfill, this is computed by sorting within the DataFrame itself
    since there are no prior rows.
    """
    # Extend lookback window to get prior recommendations
    lookback_start = start_date - timedelta(days=10)
    with open_compute_session(engine) as conn:
        prior = pd.read_sql(
            """
            SELECT mstar_id, date, recommendation AS prior_recommendation
            FROM atlas.atlas_fund_decisions_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND date < %(min_date)s
            ORDER BY mstar_id, date DESC
            """,
            conn,
            params={"start": lookback_start, "end": end_date, "min_date": start_date},
        )

    if not prior.empty:
        prior["date"] = pd.to_datetime(prior["date"]).dt.date
        # Keep only the most recent prior per fund
        latest_prior = prior.sort_values("date", ascending=False).drop_duplicates("mstar_id")
        latest_prior = latest_prior[["mstar_id", "prior_recommendation"]]
        df = df.merge(latest_prior, on="mstar_id", how="left")
    else:
        df["prior_recommendation"] = None

    df["prior_recommendation"] = df["prior_recommendation"].fillna("New")

    df["entry_trigger"] = (df["recommendation"] == "Recommended") & (
        df["prior_recommendation"] != "Recommended"
    )
    df["exit_trigger"] = (df["recommendation"] == "Exit") & (df["prior_recommendation"] != "Exit")
    df["reduce_trigger"] = (df["recommendation"] == "Reduce") & (
        df["prior_recommendation"] != "Reduce"
    )
    df["add_trigger"] = df.apply(
        lambda r: (r["prior_recommendation"], r["recommendation"]) in _UPGRADE_PAIRS,
        axis=1,
    )
    df["last_week_recommendation"] = df["prior_recommendation"]
    return df


# --------------------------------------------------------------------------- #
# Weeks in current state                                                       #
# --------------------------------------------------------------------------- #


def compute_weeks_in_state(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Count consecutive days (not weeks) in current recommendation state.

    For v0, approximated via consecutive-day count within the batch.
    Exact week-count requires full history; the UI divides by 5 to get
    approximate weeks.
    """
    df = df.sort_values(["mstar_id", "date"])

    def _streak(grp: pd.DataFrame) -> pd.Series:
        counts = []
        streak = 0
        prev = None
        for rec in grp["recommendation"]:
            if rec == prev:
                streak += 1
            else:
                streak = 1
            counts.append(streak)
            prev = rec
        return pd.Series(counts, index=grp.index)

    df["weeks_in_current_state"] = df.groupby("mstar_id", group_keys=False).apply(_streak)
    return df


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def run_fund_decisions(
    start_date: date,
    end_date: date,
    run_id: uuid.UUID | None = None,
    engine: Engine | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute fund decision columns for every (fund, date) in range."""
    engine = engine or get_engine()
    run_id = run_id or uuid.uuid4()
    if thresholds is None:
        thresholds = load_thresholds(engine)

    log.info("fund_decisions_start", start=str(start_date), end=str(end_date))

    df = _load_fund_states_with_regime(engine, start_date, end_date)
    if df.empty:
        log.warning("fund_decisions_empty_load")
        return {"run_id": run_id, "rows_written": 0, "errors": []}

    df = compute_fund_recommendations(df)
    df = compute_fund_exit_triggers(df)
    df = compute_recommendation_transitions(df, engine, start_date, end_date)
    df = compute_weeks_in_state(df)
    df["compute_run_id"] = str(run_id)

    write_cols = [c for c in DECISIONS_COLUMNS if c in df.columns]
    rows = df_to_pg_rows(df[write_cols])
    rows_written = bulk_upsert(
        engine,
        "atlas.atlas_fund_decisions_daily",
        list(write_cols),
        rows,
        pk_columns=["mstar_id", "date"],
    )

    log.info("fund_decisions_complete", rows_written=rows_written)
    return {"run_id": run_id, "rows_written": rows_written, "errors": []}


def backfill_fund_decisions(
    start_date: date | None = None,
    end_date: date | None = None,
    engine: Engine | None = None,
) -> int:
    engine = engine or get_engine()
    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()
    result = run_fund_decisions(start, end, engine=engine)
    return int(str(result["rows_written"]))
