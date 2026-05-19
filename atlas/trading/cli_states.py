"""State Engine CLI helpers — dwell/urgency wiring, baselines-refresh, tune.

# allow-large: five cohesive CLI sub-commands for state-engine ops sharing DB wiring.
# Splitting further would create import-cycle risk with atlas.trading.cli.

Split from cli.py to keep that file under the 600-LOC hook limit.
These functions are imported directly into cli.py.

Public API:
  _apply_dwell_and_urgency(panel, eng) -> pd.DataFrame
  _states_baselines_refresh_cmd(args) -> int
  _states_tune_cmd(args) -> int
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from typing import Any, cast

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from atlas.intelligence.states.threshold_optimizer import (
    apply_tuned_threshold,
    tune_single_threshold,
)
from atlas.intelligence.states.tune_catalog import TUNE_CATALOG, build_factor_panel

log = structlog.get_logger()


def _notna_scalar(v: Any) -> bool:
    """Return True if scalar v is not None / NaN / NaT (pyright-safe wrapper)."""
    return bool(pd.notna(v))


def _states_tune_cmd(args: argparse.Namespace) -> int:
    """Run IC-validation tuning across the catalog, persist optimal theta per threshold."""
    from atlas.intelligence.validation.forward_returns import (
        compute_forward_returns,
        load_price_matrix,
    )

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    as_of = date.fromisoformat(args.as_of) if args.as_of else end

    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set. Source .env first.")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    log.info("states_tune_start", start=str(start), end=str(end), as_of=str(as_of))

    # Load price matrix once; reused across all horizons.
    prices = load_price_matrix(eng, start_date=start, end_date=end)
    if prices.empty:
        log.error("states_tune_no_price_data", start=str(start), end=str(end))
        return 1

    # Pre-compute all forward-return horizons in a single pass.
    horizons = sorted({entry["horizon_days"] for entry in TUNE_CATALOG})
    fwd = compute_forward_returns(prices, periods=horizons)
    log.info("states_tune_loaded_data", n_horizons=len(horizons), n_instruments=prices.shape[1])

    summaries: list[dict[str, Any]] = []
    for entry in TUNE_CATALOG:
        tname = entry["threshold_name"]
        try:
            factor = build_factor_panel(eng, entry["factor_builder"], start, end)
        except NotImplementedError as exc:
            log.warning("states_tune_skip_builder", threshold=tname, reason=str(exc))
            summaries.append({"threshold_name": tname, "status": "skipped"})
            continue

        if factor.empty:
            log.warning("states_tune_empty_factor", threshold=tname)
            summaries.append({"threshold_name": tname, "status": "no_data"})
            continue

        returns_wide: pd.DataFrame = cast(pd.DataFrame, fwd[f"return_{entry['horizon_days']}d"])
        result = tune_single_threshold(
            threshold_name=tname,
            state=entry["state"],
            factor=factor,
            returns_wide=returns_wide,
            candidates=entry["candidates"],
            as_of=as_of,
        )
        log.info(
            "states_tune_result",
            threshold=tname,
            optimal=result.optimal_value,
            passed_gates=result.passed_gates,
        )
        if not args.dry_run:
            apply_tuned_threshold(eng, result)

        summaries.append(
            {
                "threshold_name": tname,
                "state": entry["state"],
                "optimal_value": result.optimal_value,
                "passed_gates": result.passed_gates,
                "per_candidate_ic": {
                    str(k): {kk: vv for kk, vv in v.items() if kk in ("ic_ir", "q5_q1_spread")}
                    for k, v in result.per_candidate_ic.items()
                },
            }
        )

    if args.format == "json":
        import json

        print(
            json.dumps(
                {"as_of": str(as_of), "dry_run": args.dry_run, "tuned": summaries},
                indent=2,
                default=str,
            )
        )
    else:
        print(f"=== Tuning summary as_of={as_of} (dry_run={args.dry_run}) ===")
        for s in summaries:
            print(
                f"  {s['threshold_name']:<26} -> {s.get('optimal_value')} "
                f"(passed_gates={s.get('passed_gates', 'n/a')})"
            )
    return 0


def _apply_dwell_and_urgency(
    panel: pd.DataFrame,
    eng: Any,
) -> pd.DataFrame:
    """Patch panel with real dwell_percentile, urgency_score, within_state_rank.

    Reads the latest atlas_state_dwell_statistics. If empty, fills with
    placeholders (None / 'n/a') so the row is still persistable.

    dwell_percentile: linear position within (p25, p95) range, clamped [0, 1].
    urgency_score: derive_urgency(state, dwell_days, cohort_baseline_dict).
    within_state_rank (IC-validated formula, migration 078):
      0.4 * freshness + 0.3 * rs_rank_12m + 0.3 * realized_vol_rank
      where:
        freshness        = 1 - dwell_percentile (0.5 if unavailable)
        rs_rank_12m      = cross-sectional percentile of 12m return
        realized_vol_rank = cross-sectional percentile of realized_vol_63 per-day
                           (high vol -> high rank -> favored; IR +0.55 at 63d validated)
    """
    from atlas.intelligence.states.dwell import derive_urgency

    # Determine date range covered by the panel for the realized_vol_63 join.
    panel_dates = panel["date"].unique().tolist()

    # Load latest cohort baselines.
    with eng.connect() as c:
        baselines: pd.DataFrame = cast(
            pd.DataFrame,
            pd.read_sql(
                text("""
                    SELECT cohort_key, state, median_dwell_days, p25_dwell_days,
                           p75_dwell_days, p95_dwell_days
                    FROM atlas.atlas_state_dwell_statistics
                    WHERE as_of_date = (
                        SELECT MAX(as_of_date) FROM atlas.atlas_state_dwell_statistics
                    )
                """),
                c,
            ),
        )
        meta: pd.DataFrame = cast(
            pd.DataFrame,
            pd.read_sql(
                text("""
                    SELECT instrument_id::text AS instrument_id,
                           in_nifty_100, in_nifty_500, sector
                    FROM atlas.atlas_universe_stocks
                    WHERE effective_to IS NULL OR effective_to >= CURRENT_DATE
                """),
                c,
            ),
        )
        # Load realized_vol_63 for the panel's date range.
        # Used to compute cross-sectional percentile rank per date.
        if panel_dates:
            min_date = min(panel_dates)
            max_date = max(panel_dates)
            vol_df: pd.DataFrame = cast(
                pd.DataFrame,
                pd.read_sql(
                    text("""
                        SELECT instrument_id::text AS instrument_id, date, realized_vol_63
                        FROM atlas.atlas_stock_metrics_daily
                        WHERE date BETWEEN :min_d AND :max_d
                          AND realized_vol_63 IS NOT NULL
                    """),
                    c,
                    params={"min_d": min_date, "max_d": max_date},
                ),
            )
        else:
            vol_df = pd.DataFrame(
                {
                    "instrument_id": pd.Series([], dtype=str),
                    "date": pd.Series([], dtype=object),
                    "realized_vol_63": pd.Series([], dtype=float),
                }
            )

    # ---------------------------------------------------------------------------
    # 1. Build (instrument_id, date) -> realized_vol_rank via zip dict-comp.
    #    ~30x faster than iterrows on 40k rows (500 instruments x 20 trading days).
    # ---------------------------------------------------------------------------
    realized_vol_rank_map: dict[tuple[str, Any], float] = {}
    if not vol_df.empty:
        vol_df["realized_vol_rank"] = vol_df.groupby("date")["realized_vol_63"].rank(pct=True)
        _v_iids: list[str] = vol_df["instrument_id"].astype(str).tolist()
        _v_dates: list[Any] = vol_df["date"].tolist()
        _v_ranks: list[float] = vol_df["realized_vol_rank"].astype(float).tolist()
        realized_vol_rank_map = {
            (iid, dt): rank for iid, dt, rank in zip(_v_iids, _v_dates, _v_ranks, strict=False)
        }

    # ---------------------------------------------------------------------------
    # 2. Vectorized panel enrichment — merge meta + baselines, compute all cols.
    #    Replaces two O(n) iterrows loops with vectorized merge + assign.
    # ---------------------------------------------------------------------------
    p: pd.DataFrame = panel.copy()
    p["instrument_id"] = p["instrument_id"].astype(str)

    # Attach meta (in_nifty_100, in_nifty_500, sector) via left-merge.
    meta_slim: pd.DataFrame = cast(
        pd.DataFrame,
        meta[["instrument_id", "in_nifty_100", "in_nifty_500", "sector"]].copy(),
    )
    meta_slim["instrument_id"] = meta_slim["instrument_id"].astype(str)
    p = cast(pd.DataFrame, p.merge(meta_slim, on="instrument_id", how="left"))

    # Instruments absent from meta: mark for sentinel fill.
    _no_meta = cast(pd.Series, p["in_nifty_100"].isna() & p["in_nifty_500"].isna())

    # Derive cohort_key (only 3 possible values — vectorized np.where).
    # Use numpy object arrays to avoid FutureWarning from fillna on object columns.
    _in100_arr = np.array(p["in_nifty_100"].tolist(), dtype=object)
    _in500_arr = np.array(p["in_nifty_500"].tolist(), dtype=object)
    _in100_bool = np.array(
        [
            bool(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else False
            for v in _in100_arr
        ]
    )
    _in500_bool = np.array(
        [
            bool(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else False
            for v in _in500_arr
        ]
    )
    p["_cohort_key"] = np.where(
        _in100_bool, "large_cap", np.where(_in500_bool, "mid_cap", "small_cap")
    )
    # Instruments absent from meta: sentinel -> urgency='n/a', numeric cols=None.
    p.loc[_no_meta, "_cohort_key"] = None

    # Deduplicate baselines before merging — atlas_state_dwell_statistics may have
    # duplicate (as_of_date, cohort_key, state) rows if the refresh ran more than
    # once for the same date. A cartesian explosion from the merge would double
    # panel rows and corrupt dwell_percentile / urgency_score.
    baselines = baselines.drop_duplicates(["cohort_key", "state"], keep="last").reset_index(
        drop=True
    )

    # Prepare baselines lookup DataFrame with normalised column names.
    _bl_rename: dict[str, str] = {
        "cohort_key": "_cohort_key",
        "p25_dwell_days": "_bl_p25",
        "p95_dwell_days": "_bl_p95",
        "p75_dwell_days": "_bl_p75",
        "median_dwell_days": "_bl_median",
    }
    bl: pd.DataFrame = cast(
        pd.DataFrame,
        baselines.rename(columns=_bl_rename)[
            ["_cohort_key", "state", "_bl_p25", "_bl_p95", "_bl_p75", "_bl_median"]
        ].copy(),
    )
    for _c in ("_bl_p25", "_bl_p95", "_bl_p75", "_bl_median"):
        bl[_c] = pd.to_numeric(bl[_c], errors="coerce")

    # Merge baselines on (cohort_key, state).
    p = cast(pd.DataFrame, p.merge(bl, on=["_cohort_key", "state"], how="left"))

    # Compute dwell_percentile — vectorized.
    _denom = cast(pd.Series, (p["_bl_p95"] - p["_bl_p25"]).clip(lower=1))
    _has_bl = cast(pd.Series, p["_bl_p25"].notna() & p["_bl_p95"].notna())
    _pct_raw = cast(pd.Series, (p["dwell_days"].astype(float) - p["_bl_p25"]) / _denom)
    p["dwell_percentile"] = np.where(
        _has_bl,
        _pct_raw.clip(0.0, 1.0).round(4),
        np.nan,
    )
    # NaN -> None for DB compatibility (persisted as NULL, not NaN).
    p["dwell_percentile"] = p["dwell_percentile"].where(p["dwell_percentile"].notna(), other=None)

    # Compute realized_vol_rank via pre-built map (list-comp; no iterrows).
    _p_iids: list[str] = p["instrument_id"].tolist()
    _p_dates: list[Any] = p["date"].tolist()
    p["_vol_rank"] = [
        realized_vol_rank_map.get((str(iid), dt), 0.5)
        for iid, dt in zip(_p_iids, _p_dates, strict=False)
    ]

    # Freshness and rs_rank columns.
    # Use numpy object arrays + np.where to avoid pd.to_numeric's union return type.
    _dp_obj = np.array(p["dwell_percentile"].tolist(), dtype=object)
    _dp_na = np.array([v is None or (isinstance(v, float) and np.isnan(v)) for v in _dp_obj])
    p["_freshness"] = 1.0 - np.where(_dp_na, 0.5, _dp_obj.astype(float))

    _rs_raw_col: pd.Series = cast(  # type: ignore[type-arg]
        pd.Series,
        p["rs_rank_12m"] if "rs_rank_12m" in p.columns else pd.Series(0.5, index=p.index),
    )
    _rs_obj = np.array(_rs_raw_col.tolist(), dtype=object)
    _rs_na = np.array([v is None or (isinstance(v, float) and np.isnan(v)) for v in _rs_obj])
    p["_rs"] = np.where(_rs_na, 0.5, _rs_obj.astype(float))

    # within_state_rank — fully vectorized formula (migration 078).
    p["within_state_rank"] = (0.4 * p["_freshness"] + 0.3 * p["_rs"] + 0.3 * p["_vol_rank"]).round(
        4
    )
    p.loc[_no_meta, "within_state_rank"] = None

    # urgency_score — derive_urgency is pure; one .apply pass over ~16k rows.
    def _bl_dict(row: pd.Series) -> dict[str, Any] | None:  # type: ignore[type-arg]
        p25_raw = row.get("_bl_p25")
        if p25_raw is None or (isinstance(p25_raw, float) and np.isnan(p25_raw)):
            return None

        def _si(v: Any) -> int | None:
            return int(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None

        return {
            "median": _si(row.get("_bl_median")),
            "p25": _si(row.get("_bl_p25")),
            "p75": _si(row.get("_bl_p75")),
            "p95": _si(row.get("_bl_p95")),
        }

    def _urgency_for_row(row: pd.Series) -> str:  # type: ignore[type-arg]
        n100 = row.get("in_nifty_100")
        n500 = row.get("in_nifty_500")
        _miss_100 = n100 is None or (isinstance(n100, float) and np.isnan(n100))
        _miss_500 = n500 is None or (isinstance(n500, float) and np.isnan(n500))
        if _miss_100 and _miss_500:
            return "n/a"
        return str(derive_urgency(str(row["state"]), int(row["dwell_days"]), _bl_dict(row)))

    p["urgency_score"] = p.apply(_urgency_for_row, axis=1)

    # Drop all helper/joined columns; return original schema plus three patched cols.
    _drop_cols = [
        "in_nifty_100",
        "in_nifty_500",
        "sector",
        "_cohort_key",
        "_bl_p25",
        "_bl_p95",
        "_bl_p75",
        "_bl_median",
        "_freshness",
        "_rs",
        "_vol_rank",
    ]
    p = p.drop(columns=[c for c in _drop_cols if c in p.columns])
    return p


def _states_validate_legacy_cmd(args: argparse.Namespace) -> int:
    """Run IC engine against legacy candidate signals; persist to atlas_component_validation."""
    from datetime import date as date_type
    from datetime import datetime

    from atlas.intelligence.states.ic_harness import (
        persist_legacy_ic_results,
        run_legacy_ic_harness,
    )

    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set. Source .env first.")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    start_d = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_d = datetime.strptime(args.end, "%Y-%m-%d").date()
    log.info("validate_legacy_start", start=str(start_d), end=str(end_d))

    df = run_legacy_ic_harness(eng, start_d, end_d)
    print(f"\n=== Legacy signal IC results ({start_d} -> {end_d}) ===")
    print(df.to_string(index=False))

    if not args.no_persist:
        as_of = date_type.today()
        n = persist_legacy_ic_results(eng, df, as_of_date=as_of)
        print(f"\nPersisted {n} rows to atlas_component_validation (as_of={as_of}).")

    return 0


def _states_validate_components_cmd(args: argparse.Namespace) -> int:
    """IC-validate each component tier against forward returns; print summary."""
    from atlas.intelligence.states.component_validator import validate_all_components

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set. Source .env first.")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    results = validate_all_components(eng, start, end)
    print(f"=== Component validation as_of={end} ({len(results)} rows) ===")
    print(f"{'component':<26} {'badge':<14} {'status':<22} {'ic_ir':>8} {'q5_q1':>8}")
    for r in results:
        print(
            f"  {r.component_name:<24} {r.badge:<14} {r.status:<22} "
            f"{r.ic_ir:>+8.4f} {r.q5_q1_spread:>+8.4f}"
        )
    return 0


def _states_baselines_refresh_cmd(args: Any) -> int:
    """Recompute per-cohort dwell baselines from atlas_stock_state_daily.

    Reads all historical classified rows joined with universe metadata,
    assigns cohort keys, and writes per-(cohort, state) dwell statistics
    to atlas_state_dwell_statistics for today's as_of_date.
    """
    from atlas.intelligence.states.cohorts import cohort_for_stock
    from atlas.intelligence.states.dwell import compute_cohort_dwell_baselines

    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        raise SystemExit("ATLAS_DB_URL is not set. Source .env first.")
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    eng = create_engine(db_url, pool_size=2, max_overflow=0)

    log.info("baselines_refresh_start")

    # Pull all historical state classifications joined with cohort metadata.
    with eng.connect() as c:
        df: pd.DataFrame = cast(
            pd.DataFrame,
            pd.read_sql(
                text("""
                    SELECT s.instrument_id::text AS instrument_id, s.state, s.dwell_days,
                           u.in_nifty_100, u.in_nifty_500, u.sector
                    FROM atlas.atlas_stock_state_daily s
                    JOIN atlas.atlas_universe_stocks u USING (instrument_id)
                    WHERE u.effective_to IS NULL OR u.effective_to >= CURRENT_DATE
                """),
                c,
            ),
        )

    before_rows = len(df)
    log.info("baselines_refresh_loaded", rows=before_rows)

    if df.empty:
        log.warning("baselines_refresh_no_data")
        return 1

    # Apply cohort key per row (only ~500 unique instruments -> acceptable).
    df["cohort_key"] = df.apply(
        lambda r: cohort_for_stock(
            in_nifty_100=bool(r["in_nifty_100"]),
            in_nifty_500=bool(r["in_nifty_500"]),
            sector=str(r["sector"]) if _notna_scalar(r["sector"]) else "",
        ),
        axis=1,
    )

    stats: pd.DataFrame = cast(pd.DataFrame, compute_cohort_dwell_baselines(df))
    after_rows = len(stats)
    log.info("baselines_refresh_computed", n_cohort_state_rows=after_rows)

    # Upsert into atlas_state_dwell_statistics for today's as_of_date.
    today = date.today()
    with eng.begin() as conn:
        # Clear any existing rows for today (idempotent refresh).
        conn.execute(
            text("DELETE FROM atlas.atlas_state_dwell_statistics WHERE as_of_date = :d"),
            {"d": today},
        )
        for _, r in stats.iterrows():
            _mean: Any = r["mean_dwell_days"]
            _med: Any = r["median_dwell_days"]
            _p25: Any = r["p25_dwell_days"]
            _p75: Any = r["p75_dwell_days"]
            _p95: Any = r["p95_dwell_days"]
            conn.execute(
                text("""
                    INSERT INTO atlas.atlas_state_dwell_statistics
                        (cohort_key, state, mean_dwell_days, median_dwell_days,
                         p25_dwell_days, p75_dwell_days, p95_dwell_days,
                         n_observations, as_of_date)
                    VALUES (:cohort_key, :state, :mean, :median, :p25, :p75, :p95, :n, :d)
                """),
                {
                    "cohort_key": str(r["cohort_key"]),
                    "state": str(r["state"]),
                    "mean": float(_mean) if _notna_scalar(_mean) else None,
                    "median": int(_med) if _notna_scalar(_med) else None,
                    "p25": int(_p25) if _notna_scalar(_p25) else None,
                    "p75": int(_p75) if _notna_scalar(_p75) else None,
                    "p95": int(_p95) if _notna_scalar(_p95) else None,
                    "n": int(r["n_observations"]),
                    "d": today,
                },
            )

    print(f"Baselines refreshed: {after_rows} (cohort, state) rows for as_of_date={today}")
    return 0
