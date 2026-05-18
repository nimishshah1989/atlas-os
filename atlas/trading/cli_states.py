"""State Engine CLI helpers — dwell/urgency wiring, baselines-refresh, tune.

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

import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from atlas.intelligence.states.threshold_optimizer import (
    apply_tuned_threshold,
    tune_single_threshold,
)
from atlas.intelligence.states.tune_catalog import TUNE_CATALOG, build_factor_panel

log = structlog.get_logger()


def _states_tune_cmd(args: argparse.Namespace) -> int:
    """Run IC-validation tuning across the catalog, persist optimal θ per threshold."""
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

    summaries: list[dict] = []
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

        returns_wide = fwd[f"return_{entry['horizon_days']}d"]
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
                f"  {s['threshold_name']:<26} → {s.get('optimal_value')} "
                f"(passed_gates={s.get('passed_gates', 'n/a')})"
            )
    return 0


def _apply_dwell_and_urgency(
    panel: pd.DataFrame,
    eng,
) -> pd.DataFrame:
    """Patch panel with real dwell_percentile, urgency_score, within_state_rank.

    Reads the latest atlas_state_dwell_statistics. If empty, fills with
    placeholders (None / 'n/a') so the row is still persistable.

    dwell_percentile: linear position within (p25, p95) range, clamped [0, 1].
    urgency_score: derive_urgency(state, dwell_days, cohort_baseline_dict).
    within_state_rank: simple mean of (freshness, rs_rank_12m) where
      freshness = 1 - dwell_percentile.  IC-validated weighting deferred to Phase 2.
    """
    from atlas.intelligence.states.cohorts import cohort_for_stock
    from atlas.intelligence.states.dwell import derive_urgency

    # Load latest cohort baselines.
    with eng.connect() as c:
        baselines = pd.read_sql(
            text("""
                SELECT cohort_key, state, median_dwell_days, p25_dwell_days,
                       p75_dwell_days, p95_dwell_days
                FROM atlas.atlas_state_dwell_statistics
                WHERE as_of_date = (
                    SELECT MAX(as_of_date) FROM atlas.atlas_state_dwell_statistics
                )
            """),
            c,
        )
        meta = pd.read_sql(
            text("""
                SELECT instrument_id::text AS instrument_id,
                       in_nifty_100, in_nifty_500, sector
                FROM atlas.atlas_universe_stocks
                WHERE effective_to IS NULL OR effective_to >= CURRENT_DATE
            """),
            c,
        )

    # Build meta lookup: instrument_id -> row dict.
    meta_map: dict[str, dict] = {}
    for _, r in meta.iterrows():
        meta_map[str(r["instrument_id"])] = r.to_dict()

    # Build baseline lookup: (cohort_key, state) -> {p25, p75, p95, ...}.
    baseline_lookup: dict[tuple[str, str], dict] = {}
    for _, r in baselines.iterrows():
        baseline_lookup[(r["cohort_key"], r["state"])] = {
            "median": int(r["median_dwell_days"]) if pd.notna(r["median_dwell_days"]) else None,
            "p25": int(r["p25_dwell_days"]) if pd.notna(r["p25_dwell_days"]) else None,
            "p75": int(r["p75_dwell_days"]) if pd.notna(r["p75_dwell_days"]) else None,
            "p95": int(r["p95_dwell_days"]) if pd.notna(r["p95_dwell_days"]) else None,
        }

    dwell_pct: list[float | None] = []
    urgency: list[str] = []
    within_rank: list[float | None] = []

    for _, r in panel.iterrows():
        iid = str(r["instrument_id"])
        m = meta_map.get(iid)
        if m is None:
            dwell_pct.append(None)
            urgency.append("n/a")
            within_rank.append(None)
            continue

        cohort = cohort_for_stock(
            in_nifty_100=bool(m["in_nifty_100"]),
            in_nifty_500=bool(m["in_nifty_500"]),
            sector=m["sector"] or "",
        )
        baseline = baseline_lookup.get((cohort, r["state"]))

        # urgency_score
        urgency.append(derive_urgency(r["state"], int(r["dwell_days"]), baseline))

        # dwell_percentile: linear position within (p25, p95) range.
        if baseline and baseline.get("p25") is not None and baseline.get("p95") is not None:
            p25 = baseline["p25"]
            p95 = baseline["p95"]
            denom = max(p95 - p25, 1)
            pct = max(0.0, min(1.0, (int(r["dwell_days"]) - p25) / denom))
            dwell_pct.append(round(pct, 4))
        else:
            dwell_pct.append(None)

        # within_state_rank: mean of freshness + rs_rank_12m.
        # freshness = 1 - dwell_percentile (0.5 if unavailable).
        fresh = 1.0 - (dwell_pct[-1] if dwell_pct[-1] is not None else 0.5)
        rs_raw = r.get("rs_rank_12m")
        if rs_raw is None or (isinstance(rs_raw, float) and pd.isna(rs_raw)):
            rs = 0.5
        else:
            rs = float(rs_raw)
        within_rank.append(round((fresh + rs) / 2.0, 4))

    panel = panel.copy()
    panel["dwell_percentile"] = dwell_pct
    panel["urgency_score"] = urgency
    panel["within_state_rank"] = within_rank
    return panel


def _states_baselines_refresh_cmd(args) -> int:
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
        df = pd.read_sql(
            text("""
                SELECT s.instrument_id::text AS instrument_id, s.state, s.dwell_days,
                       u.in_nifty_100, u.in_nifty_500, u.sector
                FROM atlas.atlas_stock_state_daily s
                JOIN atlas.atlas_universe_stocks u USING (instrument_id)
                WHERE u.effective_to IS NULL OR u.effective_to >= CURRENT_DATE
            """),
            c,
        )

    before_rows = len(df)
    log.info("baselines_refresh_loaded", rows=before_rows)

    if df.empty:
        log.warning("baselines_refresh_no_data")
        return 1

    # Apply cohort key per row (only ~500 unique instruments → acceptable).
    df["cohort_key"] = df.apply(
        lambda r: cohort_for_stock(
            in_nifty_100=bool(r["in_nifty_100"]),
            in_nifty_500=bool(r["in_nifty_500"]),
            sector=r["sector"] or "",
        ),
        axis=1,
    )

    stats = compute_cohort_dwell_baselines(df)
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
            conn.execute(
                text("""
                    INSERT INTO atlas.atlas_state_dwell_statistics
                        (cohort_key, state, mean_dwell_days, median_dwell_days,
                         p25_dwell_days, p75_dwell_days, p95_dwell_days,
                         n_observations, as_of_date)
                    VALUES (:cohort_key, :state, :mean, :median, :p25, :p75, :p95, :n, :d)
                """),
                {
                    "cohort_key": r["cohort_key"],
                    "state": r["state"],
                    "mean": float(r["mean_dwell_days"]) if pd.notna(r["mean_dwell_days"]) else None,
                    "median": (
                        int(r["median_dwell_days"]) if pd.notna(r["median_dwell_days"]) else None
                    ),
                    "p25": int(r["p25_dwell_days"]) if pd.notna(r["p25_dwell_days"]) else None,
                    "p75": int(r["p75_dwell_days"]) if pd.notna(r["p75_dwell_days"]) else None,
                    "p95": int(r["p95_dwell_days"]) if pd.notna(r["p95_dwell_days"]) else None,
                    "n": int(r["n_observations"]),
                    "d": today,
                },
            )

    print(f"Baselines refreshed: {after_rows} (cohort, state) rows for as_of_date={today}")
    return 0
