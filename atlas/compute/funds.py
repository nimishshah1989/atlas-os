"""Fund pipeline orchestration — M4 Phase D.

Per ``docs/00_METHODOLOGY_LOCK.md`` §12.4 and
``docs/milestones/ATLAS_M4_MUTUAL_FUND_LENSES.md`` §7.

Assembles the three-tuple fund state (nav_state, composition_state,
holdings_state) in ``atlas_fund_states_daily``. Tracks separate refresh
dates for each lens so the UI can show "composition state as of Apr 30".

Refresh cadence:
  Lens 1 (nav_state)           — daily (NAV updates every trading day)
  Lens 2 (composition_state)   — monthly (on new holdings disclosure)
  Lens 3 (holdings_state)      — monthly (on new holdings disclosure)

The nightly ``run_m4_daily()`` always refreshes Lens 1. It checks whether
any new holdings disclosures arrived since the last Lens 2/3 run; if so,
it reruns Lens 2 and Lens 3 for the new disclosure cycle before assembling
the state tuple.
"""

from __future__ import annotations

import bisect
import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import bulk_upsert, df_to_pg_rows, open_compute_session
from atlas.compute.lens_composition import run_lens2
from atlas.compute.lens_holdings import run_lens3
from atlas.compute.lens_nav import run_lens1
from atlas.db import get_engine, load_thresholds

log = structlog.get_logger()

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

STATES_COLUMNS: tuple[str, ...] = (
    "mstar_id",
    "date",
    "category_name",
    "nav_state",
    "nav_state_as_of",
    "composition_state",
    "composition_as_of",
    "holdings_state",
    "holdings_as_of",
    "compute_run_id",
)


# --------------------------------------------------------------------------- #
# State assembly                                                               #
# --------------------------------------------------------------------------- #


def assemble_fund_states(
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Assemble three-tuple fund states for all funds × dates in [start, end].

    nav_state        — from atlas_fund_metrics_daily (latest row per fund-date)
    composition_state — from atlas_fund_lens_monthly (most recent as_of_date <= date)
    holdings_state   — from atlas_fund_lens_monthly (most recent as_of_date <= date)

    For backfill the cartesian product is split into per-fund queries to avoid
    a massive ~1.2M-row query. For daily, operates on a single date.
    """
    with open_compute_session(engine) as conn:
        funds = pd.read_sql(
            """
            SELECT mstar_id, category_name
            FROM atlas.atlas_universe_funds
            WHERE effective_to IS NULL
            ORDER BY mstar_id
            """,
            conn,
        )

    if funds.empty:
        return pd.DataFrame()

    # Get trading dates from the regime table (reliable proxy for market days)
    with open_compute_session(engine) as conn:
        dates_df = pd.read_sql(
            """
            SELECT DISTINCT date
            FROM atlas.atlas_market_regime_daily
            WHERE date BETWEEN %(start)s AND %(end)s
            ORDER BY date
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )
    trading_dates = sorted(dates_df["date"].tolist())

    if not trading_dates:
        log.warning("fund_states_no_trading_dates", start=str(start_date), end=str(end_date))
        return pd.DataFrame()

    all_states: list[pd.DataFrame] = []
    chunk_size = 50  # Process 50 funds at a time to manage memory

    for chunk_start in range(0, len(funds), chunk_size):
        chunk = funds.iloc[chunk_start : chunk_start + chunk_size]
        mstar_ids = chunk["mstar_id"].tolist()
        cat_map = dict(zip(chunk["mstar_id"], chunk["category_name"], strict=False))

        # Load Lens 1 nav metrics with a 10-day lookback so funds whose
        # latest NAV trails by a day or two (T-1 settlement, bank holiday)
        # are still included rather than silently dropped.
        nav_lookback_start = start_date - timedelta(days=10)
        with open_compute_session(engine) as conn:
            nav_metrics = pd.read_sql(
                """
                SELECT mstar_id, nav_date AS date, nav_state
                FROM atlas.atlas_fund_metrics_daily
                WHERE mstar_id = ANY(%(ids)s)
                  AND nav_date BETWEEN %(start)s AND %(end)s
                """,
                conn,
                params={"ids": mstar_ids, "start": nav_lookback_start, "end": end_date},
            )

        # Load Lens 2+3 monthly states for this fund chunk
        with open_compute_session(engine) as conn:
            monthly_states = pd.read_sql(
                """
                SELECT mstar_id, as_of_date,
                       composition_state, holdings_state
                FROM atlas.atlas_fund_lens_monthly
                WHERE mstar_id = ANY(%(ids)s)
                  AND as_of_date <= %(end)s
                ORDER BY mstar_id, as_of_date
                """,
                conn,
                params={"ids": mstar_ids, "end": end_date},
            )

        # Build state for each (fund, date) in the chunk.
        # nav_state: use most recent row on or before the trading date (within
        # max_nav_staleness_days) so funds whose NAV trails by T-1/T-2 due
        # to settlement lag or bank holidays are not silently dropped.
        max_nav_staleness_days = 10

        for mstar_id in mstar_ids:
            fund_nav = nav_metrics[nav_metrics["mstar_id"] == mstar_id].copy()
            fund_monthly = monthly_states[monthly_states["mstar_id"] == mstar_id].copy()

            fund_nav_sorted = fund_nav.sort_values("date").reset_index(drop=True)
            nav_dates_list: list[date] = fund_nav_sorted["date"].tolist()

            monthly_sorted = fund_monthly.sort_values("as_of_date")

            rows = []
            for d in trading_dates:
                # Binary-search for the latest nav row on or before d.
                # bisect_right returns insertion point after any equal elements,
                # so -1 gives the last row whose date <= d.
                idx = bisect.bisect_right(nav_dates_list, d) - 1  # type: ignore[attr-defined]
                if idx < 0:
                    continue
                latest_nav_row = fund_nav_sorted.iloc[idx]
                days_stale = (d - latest_nav_row["date"]).days
                if days_stale > max_nav_staleness_days:
                    continue
                nav_s = latest_nav_row["nav_state"]
                nav_as_of = latest_nav_row["date"]

                # table column is NOT NULL — skip if classifier produced None
                if nav_s is None:
                    continue

                # Most recent monthly disclosure on or before d.
                avail = monthly_sorted[monthly_sorted["as_of_date"] <= d]
                if not avail.empty:
                    latest = avail.iloc[-1]
                    comp_s = latest["composition_state"] or "NO_DISCLOSURE"
                    hold_s = latest["holdings_state"] or "NO_DISCLOSURE"
                    comp_as_of = latest["as_of_date"]
                    hold_as_of = latest["as_of_date"]
                else:
                    comp_s = "NO_DISCLOSURE"
                    hold_s = "NO_DISCLOSURE"
                    comp_as_of = None
                    hold_as_of = None

                rows.append(
                    {
                        "mstar_id": mstar_id,
                        "date": d,
                        "category_name": cat_map[mstar_id],
                        "nav_state": nav_s,
                        "nav_state_as_of": nav_as_of,
                        "composition_state": comp_s,
                        "composition_as_of": comp_as_of,
                        "holdings_state": hold_s,
                        "holdings_as_of": hold_as_of,
                    }
                )

            if rows:
                all_states.append(pd.DataFrame(rows))

        log.debug(
            "fund_states_chunk_done",
            chunk_start=chunk_start,
            chunk_size=len(chunk),
            dates=len(trading_dates),
        )

    if not all_states:
        return pd.DataFrame()

    return pd.concat(all_states, ignore_index=True)


def apply_dislocation_override(
    fund_states: pd.DataFrame,
    engine: Engine,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Override all state columns to DISLOCATION_SUSPENDED when regime is active.

    Per methodology §12.4: suspension applies to fund states the same way
    it applies to stock/ETF states in M2.
    """
    with open_compute_session(engine) as conn:
        regime = pd.read_sql(
            """
            SELECT date, dislocation_active
            FROM atlas.atlas_market_regime_daily
            WHERE date BETWEEN %(start)s AND %(end)s
              AND dislocation_active = TRUE
            """,
            conn,
            params={"start": start_date, "end": end_date},
        )

    if regime.empty:
        return fund_states

    suspended_dates = set(regime["date"])
    state_cols = ["nav_state", "composition_state", "holdings_state"]
    mask = fund_states["date"].isin(suspended_dates)

    df = fund_states.copy()
    for col in state_cols:
        df.loc[mask, col] = "DISLOCATION_SUSPENDED"

    suspended_rows = int(mask.sum())
    log.info("dislocation_override_applied", rows=suspended_rows)
    return df


# --------------------------------------------------------------------------- #
# Run helpers                                                                  #
# --------------------------------------------------------------------------- #


def _check_new_disclosures(engine: Engine) -> bool:
    """Return True if any new holdings disclosures arrived since last lens run."""
    with open_compute_session(engine) as conn:
        result = conn.execute(
            __import__("sqlalchemy").text("""
            SELECT COUNT(*) FROM public.de_mf_holdings
            WHERE as_of_date > (
                SELECT COALESCE(MAX(last_disclosed_date), '2014-01-01'::date)
                FROM atlas.atlas_fund_lens_monthly
            )
            """)
        ).scalar()
    return int(result or 0) > 0


def run_m4_daily(
    target_date: date | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """M4 nightly pipeline for a single target date.

    1. Refresh Lens 1 (NAV) for target_date.
    2. If new holdings disclosures exist: refresh Lens 2 + Lens 3.
    3. Assemble three-tuple state for target_date.
    4. Apply dislocation override.
    5. Upsert to atlas_fund_states_daily.
    """
    engine = engine or get_engine()
    run_id = uuid.uuid4()
    target_date = target_date or date.today()
    thresholds = load_thresholds(engine)

    log.info("m4_daily_start", date=str(target_date), run_id=str(run_id))

    # Stage 7a: Lens 1
    lens1_result = run_lens1(
        start_date=target_date,
        end_date=target_date,
        run_id=run_id,
        engine=engine,
        thresholds=thresholds,
    )

    # Stage 7b/7c: Lens 2 + 3 if new disclosures
    lens2_result: dict[str, Any] = {"rows_written": 0, "skipped": True}
    lens3_result: dict[str, Any] = {"rows_written": 0, "skipped": True}
    if _check_new_disclosures(engine):
        log.info("m4_new_disclosures_detected")
        lens2_result = run_lens2(
            end_date=target_date,
            run_id=run_id,
            engine=engine,
            thresholds=thresholds,
        )
        lens3_result = run_lens3(
            end_date=target_date,
            run_id=run_id,
            engine=engine,
            thresholds=thresholds,
        )

    # Stage 7d: State assembly
    fund_states = assemble_fund_states(engine, target_date, target_date)
    if fund_states.empty:
        log.warning("m4_daily_no_states", date=str(target_date))
        return {"run_id": run_id, "rows_written": 0, "status": "no_states"}

    fund_states = apply_dislocation_override(fund_states, engine, target_date, target_date)
    fund_states["compute_run_id"] = str(run_id)

    write_cols = [c for c in STATES_COLUMNS if c in fund_states.columns]
    rows = df_to_pg_rows(fund_states[write_cols])
    rows_written = bulk_upsert(
        engine,
        "atlas.atlas_fund_states_daily",
        list(write_cols),
        rows,
        pk_columns=["mstar_id", "date"],
    )

    log.info(
        "m4_daily_complete",
        date=str(target_date),
        lens1_rows=lens1_result["rows_written"],
        lens2_rows=lens2_result["rows_written"],
        lens3_rows=lens3_result["rows_written"],
        state_rows=rows_written,
    )
    return {
        "run_id": run_id,
        "rows_written": rows_written,
        "lens1": lens1_result,
        "lens2": lens2_result,
        "lens3": lens3_result,
        "status": "ok",
    }


def run_m4_backfill(
    start_date: date | None = None,
    end_date: date | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Full historical backfill: Lens 1 → Lens 2 → Lens 3 → State assembly.

    Default date range: 2014-04-01 → today.
    """
    from atlas.config import Config

    engine = engine or get_engine()
    run_id = uuid.uuid4()
    start = start_date or pd.to_datetime(Config.HISTORICAL_START_DATE).date()
    end = end_date or date.today()
    thresholds = load_thresholds(engine)

    log.info("m4_backfill_start", start=str(start), end=str(end), run_id=str(run_id))

    # Phase 1: Lens 1 NAV metrics for all funds × all dates
    lens1 = run_lens1(
        start_date=start,
        end_date=end,
        run_id=run_id,
        engine=engine,
        thresholds=thresholds,
    )
    log.info("m4_backfill_lens1_done", rows=lens1["rows_written"])

    # Phase 2: Lens 2 + Lens 3 for all historical disclosures
    lens2 = run_lens2(
        start_date=start,
        end_date=end,
        run_id=run_id,
        engine=engine,
        thresholds=thresholds,
    )
    log.info("m4_backfill_lens2_done", rows=lens2["rows_written"])

    lens3 = run_lens3(
        start_date=start,
        end_date=end,
        run_id=run_id,
        engine=engine,
        thresholds=thresholds,
    )
    log.info("m4_backfill_lens3_done", rows=lens3["rows_written"])

    # Phase 3: Three-tuple state assembly
    fund_states = assemble_fund_states(engine, start, end)
    if not fund_states.empty:
        fund_states = apply_dislocation_override(fund_states, engine, start, end)
        fund_states["compute_run_id"] = str(run_id)

        write_cols = [c for c in STATES_COLUMNS if c in fund_states.columns]
        rows = df_to_pg_rows(fund_states[write_cols])
        state_rows = bulk_upsert(
            engine,
            "atlas.atlas_fund_states_daily",
            list(write_cols),
            rows,
            pk_columns=["mstar_id", "date"],
        )
    else:
        state_rows = 0

    log.info(
        "m4_backfill_complete",
        lens1_rows=lens1["rows_written"],
        lens2_rows=lens2["rows_written"],
        lens3_rows=lens3["rows_written"],
        state_rows=state_rows,
    )
    return {
        "run_id": run_id,
        "lens1_rows": lens1["rows_written"],
        "lens2_rows": lens2["rows_written"],
        "lens3_rows": lens3["rows_written"],
        "state_rows": state_rows,
    }
