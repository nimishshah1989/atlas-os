"""Lens 4 — Holdings Decisions (MF Holdings History Task 2).

Diffs consecutive mutual fund holdings disclosures, derives signal quality
from RS/momentum states at action time, and computes a per-fund decision score.

Writes to:
  - ``atlas.atlas_fund_holdings_changes`` — one row per changed holding per period
  - ``atlas.atlas_fund_decision_scores`` — one aggregated score row per fund per period

Entry point: ``run_lens_decisions(engine, thresholds, target_funds)``
"""

from __future__ import annotations

from collections.abc import Mapping
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

_HIGH_QUALITY_STATES: frozenset[str] = frozenset({"Leader", "Strong", "Emerging"})
_LOW_QUALITY_STATES: frozenset[str] = frozenset({"Weak", "Laggard"})

_CHANGES_COLUMNS: tuple[str, ...] = (
    "mstar_id",
    "from_date",
    "to_date",
    "instrument_id",
    "symbol",
    "action",
    "weight_before",
    "weight_after",
    "weight_delta",
    "rs_state_at_action",
    "momentum_state_at_action",
    "signal_quality",
)

_DIFF_RESULT_COLUMNS: tuple[str, ...] = (
    "instrument_id",
    "symbol",
    "action",
    "weight_before",
    "weight_after",
    "weight_delta",
    "rs_state_at_action",
    "momentum_state_at_action",
    "signal_quality",
)

_SCORES_COLUMNS: tuple[str, ...] = (
    "mstar_id",
    "period_date",
    "entries_count",
    "exits_count",
    "increases_count",
    "decreases_count",
    "quality_entries_pct",
    "quality_exits_pct",
    "signal_score",
    "decision_state",
)

# --------------------------------------------------------------------------- #
# Loaders                                                                      #
# --------------------------------------------------------------------------- #


def _load_fund_disclosure_dates(engine: Engine, mstar_id: str) -> list[date]:
    """Return all distinct as_of_date values for a fund, newest first."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT DISTINCT as_of_date
            FROM public.de_mf_holdings
            WHERE mstar_id = %(mstar_id)s
            ORDER BY as_of_date DESC
            """,
            conn,
            params={"mstar_id": mstar_id},
        )
    return df["as_of_date"].tolist()


def _load_snapshot(
    engine: Engine,
    mstar_id: str,
    as_of_date: date,
) -> pd.DataFrame:
    """Return holdings for one fund on one date.

    Columns: instrument_id (text), symbol, weight_pct.
    Falls back to instrument_id as symbol when not in universe.
    """
    with open_compute_session(engine) as conn:
        return pd.read_sql(
            """
            SELECT
                h.instrument_id::text AS instrument_id,
                COALESCE(u.symbol, h.instrument_id::text) AS symbol,
                h.weight_pct
            FROM public.de_mf_holdings h
            LEFT JOIN atlas.atlas_universe_stocks u
                ON u.instrument_id = h.instrument_id
               AND u.effective_to IS NULL
            WHERE h.mstar_id = %(mstar_id)s
              AND h.as_of_date = %(as_of_date)s
              AND h.instrument_id IS NOT NULL
            """,
            conn,
            params={"mstar_id": mstar_id, "as_of_date": as_of_date},
        )


def _load_stock_states(
    engine: Engine,
    instrument_ids: list[str],
    as_of_date: date,
) -> dict[str, tuple[str, str]]:
    """Return {instrument_id: (rs_state, momentum_state)} for stocks on or before as_of_date.

    Uses DISTINCT ON to get the most recent row per stock.
    """
    if not instrument_ids:
        return {}

    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT DISTINCT ON (instrument_id)
                instrument_id::text AS instrument_id,
                rs_state,
                momentum_state
            FROM atlas.atlas_stock_states_daily
            WHERE instrument_id::text = ANY(%(ids)s)
              AND date <= %(date)s
            ORDER BY instrument_id, date DESC
            """,
            conn,
            params={"ids": instrument_ids, "date": as_of_date},
        )
    return dict(
        zip(
            df["instrument_id"],
            zip(df["rs_state"], df["momentum_state"], strict=False),
            strict=False,
        )
    )


def _load_computed_set(engine: Engine) -> set[tuple[str, Any]]:
    """Return set of (mstar_id, period_date) already in atlas_fund_decision_scores.

    Load once before the fund loop to enable idempotent skipping.
    """
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            "SELECT mstar_id, period_date FROM atlas.atlas_fund_decision_scores",
            conn,
        )
    if df.empty:
        return set()
    return set(zip(df["mstar_id"], df["period_date"], strict=False))


# --------------------------------------------------------------------------- #
# Core diff computation                                                        #
# --------------------------------------------------------------------------- #


def compute_holdings_diff(
    to_df: pd.DataFrame,
    from_df: pd.DataFrame,
    state_map: dict[str, tuple[str, str]],
    min_weight_delta_pct: float,
) -> pd.DataFrame:
    """Diff two holdings snapshots and classify each change.

    Args:
        to_df: Newer snapshot. Columns: instrument_id, symbol, weight_pct.
        from_df: Older snapshot (empty DataFrame for first-ever disclosure).
        state_map: {instrument_id: (rs_state, momentum_state)} as of to_df date.
        min_weight_delta_pct: Minimum absolute weight delta to count as increase/decrease.

    Returns:
        DataFrame with one row per material change. Columns:
        instrument_id, symbol, action, weight_before, weight_after,
        weight_delta, rs_state_at_action, momentum_state_at_action, signal_quality.
        Returns empty DataFrame with those columns if no rows pass the filter.
    """
    _empty_result = pd.DataFrame(columns=list(_DIFF_RESULT_COLUMNS))  # type: ignore[call-overload]

    # Normalise empty frames so the outer merge always has the right columns
    if to_df.empty:
        to_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
    if from_df.empty:
        from_df = pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]

    # If both snapshots are empty there is nothing to diff
    if to_df.empty and from_df.empty:
        return _empty_result

    merged = to_df.merge(
        from_df[["instrument_id", "weight_pct"]],
        on="instrument_id",
        how="outer",
        suffixes=("_after", "_before"),
    )

    # Fill NaN weights: exited stocks have 0 after; new entries have 0 before.
    # Use .astype(float) first to avoid pandas FutureWarning on object-dtype fillna.
    merged["weight_pct_after"] = merged["weight_pct_after"].astype(float).fillna(0.0)
    merged["weight_pct_before"] = merged["weight_pct_before"].astype(float).fillna(0.0)

    # Symbols may be NaN for rows that came only from from_df — fill from instrument_id
    merged["symbol"] = merged["symbol"].where(
        merged["symbol"].notna(), other=merged["instrument_id"]
    )

    # Vectorized delta
    merged["delta"] = merged["weight_pct_after"] - merged["weight_pct_before"]

    # Vectorized action classification (conservative-first ordering)
    is_entry = (merged["weight_pct_before"] == 0) & (merged["weight_pct_after"] > 0)
    is_exit = (merged["weight_pct_before"] > 0) & (merged["weight_pct_after"] == 0)
    is_increase = ~is_entry & ~is_exit & (merged["delta"] >= min_weight_delta_pct)
    is_decrease = ~is_entry & ~is_exit & (merged["delta"] <= -min_weight_delta_pct)

    merged["action"] = np.select(
        [is_entry, is_exit, is_increase, is_decrease],
        ["entry", "exit", "increase", "decrease"],
        default=None,  # type: ignore[arg-type]  # None rows filtered by .notna() below
    )
    merged = merged[merged["action"].notna()].copy()

    if merged.empty:
        return _empty_result

    # Vectorized state mapping — explicit Series cast avoids Pyright ndarray inference
    rs_map = {k: v[0] for k, v in state_map.items()}
    mom_map = {k: v[1] for k, v in state_map.items()}
    _ids = pd.Series(merged["instrument_id"])
    merged["rs_state"] = _ids.map(rs_map)  # type: ignore[arg-type]
    merged["mom_state"] = _ids.map(mom_map)  # type: ignore[arg-type]
    _rs = pd.Series(merged["rs_state"])

    # Vectorized signal quality — entry into strong state is high; exit from weak state is high
    _high = list(_HIGH_QUALITY_STATES)
    _low = list(_LOW_QUALITY_STATES)
    sq_conds = [
        (merged["action"] == "entry") & _rs.isin(_high),
        (merged["action"] == "entry") & _rs.isin(_low),
        (merged["action"] == "exit") & _rs.isin(_low),
        (merged["action"] == "exit") & _rs.isin(_high),
    ]
    merged["signal_quality"] = np.select(
        sq_conds, ["high", "low", "high", "low"], default="neutral"
    )

    # Rename columns to final schema names
    merged = merged.rename(  # type: ignore[call-overload]
        columns={
            "weight_pct_before": "weight_before",
            "weight_pct_after": "weight_after",
            "delta": "weight_delta",
            "rs_state": "rs_state_at_action",
            "mom_state": "momentum_state_at_action",
        }
    )
    result: pd.DataFrame = merged[list(_DIFF_RESULT_COLUMNS)].reset_index(drop=True)  # type: ignore[assignment]
    return result


# --------------------------------------------------------------------------- #
# Decision score aggregation                                                   #
# --------------------------------------------------------------------------- #


def compute_decision_score(
    diff_df: pd.DataFrame,
    mstar_id: str,
    to_date: date,
    _from_date: date | None,
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate diff results into one decision score row.

    Args:
        diff_df: Output of compute_holdings_diff.
        mstar_id: Fund identifier.
        to_date: Newer snapshot date (written as period_date).
        from_date: Older snapshot date (None for first disclosure).
        thresholds: Atlas thresholds dict.

    Returns:
        Dict matching atlas_fund_decision_scores column set.
    """
    sharp_threshold = float(thresholds["decision_score_sharp_threshold"])
    poor_threshold = float(thresholds["decision_score_poor_threshold"])

    if diff_df.empty:
        actions = pd.Series(dtype=str)
    else:
        actions = diff_df["action"]

    entries_count = int((actions == "entry").sum())
    exits_count = int((actions == "exit").sum())
    increases_count = int((actions == "increase").sum())
    decreases_count = int((actions == "decrease").sum())

    quality_entries_pct: float | None = None
    quality_exits_pct: float | None = None

    if entries_count > 0 and not diff_df.empty:
        entry_rows = diff_df[diff_df["action"] == "entry"]
        quality_entries_pct = 100.0 * (entry_rows["signal_quality"] == "high").sum() / entries_count

    if exits_count > 0 and not diff_df.empty:
        exit_rows = diff_df[diff_df["action"] == "exit"]
        quality_exits_pct = 100.0 * (exit_rows["signal_quality"] == "high").sum() / exits_count

    if quality_entries_pct is not None and quality_exits_pct is not None:
        signal_score: float | None = (quality_entries_pct + quality_exits_pct) / 2.0
    elif quality_entries_pct is not None:
        signal_score = quality_entries_pct
    elif quality_exits_pct is not None:
        signal_score = quality_exits_pct
    else:
        signal_score = None

    decision_state: str | None = None
    if signal_score is not None:
        if signal_score >= sharp_threshold:
            decision_state = "Sharp"
        elif signal_score < poor_threshold:
            decision_state = "Poor"
        else:
            decision_state = "Average"

    return {
        "mstar_id": mstar_id,
        "period_date": to_date,
        "entries_count": entries_count,
        "exits_count": exits_count,
        "increases_count": increases_count,
        "decreases_count": decreases_count,
        "quality_entries_pct": quality_entries_pct,
        "quality_exits_pct": quality_exits_pct,
        "signal_score": signal_score,
        "decision_state": decision_state,
    }


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def run_lens_decisions(
    engine: Engine | None = None,
    thresholds: Mapping[str, Any] | None = None,
    target_funds: list[str] | None = None,
) -> dict[str, Any]:
    """Compute holdings diffs and decision scores for all (or target) funds.

    Algorithm:
    1. Load already-computed (mstar_id, period_date) pairs once.
    2. For each fund, load the two most recent disclosure snapshots.
    3. Diff them, classify changes, compute a decision score.
    4. Upsert into atlas_fund_holdings_changes and atlas_fund_decision_scores.
    5. Return run summary.

    Args:
        engine: SQLAlchemy engine (created from env if None).
        thresholds: Atlas thresholds dict (loaded from DB if None).
        target_funds: If provided, process only these mstar_ids.

    Returns:
        {"funds_processed": int, "rows_written": int, "errors": list}
    """
    engine = engine or get_engine()
    thresholds = thresholds or load_thresholds("atlas", engine)

    _required = {
        "holdings_weight_change_min_pct",
        "decision_score_sharp_threshold",
        "decision_score_poor_threshold",
    }
    _missing = _required - thresholds.keys()
    if _missing:
        raise KeyError(f"Missing required thresholds: {_missing}")

    min_weight_delta = float(thresholds["holdings_weight_change_min_pct"])

    # Load all distinct funds from holdings table
    with open_compute_session(engine) as conn:
        if target_funds:
            funds_df = pd.read_sql(
                "SELECT DISTINCT mstar_id FROM public.de_mf_holdings"
                " WHERE mstar_id = ANY(%(funds)s)",
                conn,
                params={"funds": target_funds},
            )
        else:
            funds_df = pd.read_sql(
                "SELECT DISTINCT mstar_id FROM public.de_mf_holdings",
                conn,
            )

    all_funds: list[str] = funds_df["mstar_id"].tolist()

    # Load computed set once to enable idempotent skipping
    computed_set = _load_computed_set(engine)

    log.info("lens_decisions_start", total_funds=len(all_funds), already_computed=len(computed_set))

    funds_processed = 0
    total_rows_written = 0
    errors: list[dict[str, Any]] = []

    for mstar_id in all_funds:
        try:
            dates = _load_fund_disclosure_dates(engine, mstar_id)

            if len(dates) < 1:
                log.debug("lens_decisions_skip_no_dates", mstar_id=mstar_id)
                continue

            to_date: date = dates[0]
            from_date: date | None = dates[1] if len(dates) >= 2 else None

            # Idempotent skip — already computed for this fund/period
            if (mstar_id, to_date) in computed_set:
                log.debug("lens_decisions_skip_computed", mstar_id=mstar_id, to_date=str(to_date))
                continue

            # Load snapshots
            to_df = _load_snapshot(engine, mstar_id, to_date)
            from_df = (
                _load_snapshot(engine, mstar_id, from_date)
                if from_date is not None
                else pd.DataFrame(columns=["instrument_id", "symbol", "weight_pct"])  # type: ignore[call-overload]
            )

            # Load stock states as of to_date for all instruments in newer snapshot
            instrument_ids: list[str] = to_df["instrument_id"].dropna().tolist()
            state_map = _load_stock_states(engine, instrument_ids, to_date)

            before_count = len(to_df)
            # Diff
            diff_df = compute_holdings_diff(to_df, from_df, state_map, min_weight_delta)
            after_count = len(diff_df)
            log.debug(
                "lens_decisions_diff",
                mstar_id=mstar_id,
                to_date=str(to_date),
                holdings_before=before_count,
                changes_after=after_count,
            )

            # Compute decision score
            score_row = compute_decision_score(diff_df, mstar_id, to_date, from_date, thresholds)

            # Prepare change rows
            rows_written = 0
            if not diff_df.empty:
                change_rows_df = diff_df.copy()
                change_rows_df["mstar_id"] = mstar_id
                change_rows_df["from_date"] = from_date
                change_rows_df["to_date"] = to_date

                # Select columns in the exact order expected by bulk_upsert
                change_cols = list(_CHANGES_COLUMNS)
                change_rows = df_to_pg_rows(change_rows_df[change_cols])  # type: ignore[arg-type]

                rows_written += bulk_upsert(
                    engine,
                    "atlas.atlas_fund_holdings_changes",
                    change_cols,
                    change_rows,
                    pk_columns=["mstar_id", "to_date", "instrument_id"],
                )

            # Upsert decision score
            score_df = pd.DataFrame([score_row])
            score_cols = list(_SCORES_COLUMNS)
            score_rows = df_to_pg_rows(score_df[score_cols])  # type: ignore[arg-type]
            rows_written += bulk_upsert(
                engine,
                "atlas.atlas_fund_decision_scores",
                score_cols,
                score_rows,
                pk_columns=["mstar_id", "period_date"],
            )

            # Mark as computed within this run to prevent reprocessing
            computed_set.add((mstar_id, to_date))
            funds_processed += 1
            total_rows_written += rows_written

            log.info(
                "lens_decisions_fund_done",
                mstar_id=mstar_id,
                to_date=str(to_date),
                from_date=str(from_date),
                rows_written=rows_written,
                decision_state=score_row.get("decision_state"),
            )

        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"mstar_id": mstar_id, "error": str(exc)})
            log.error("lens_decisions_fund_error", mstar_id=mstar_id, error=str(exc))

    log.info(
        "lens_decisions_complete",
        funds_processed=funds_processed,
        rows_written=total_rows_written,
        errors=len(errors),
    )

    return {
        "funds_processed": funds_processed,
        "rows_written": total_rows_written,
        "errors": errors,
    }
