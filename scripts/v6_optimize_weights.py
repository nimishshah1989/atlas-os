"""Plan 2 Phase 10 — Bayesian shrinkage weight optimization.

Run after Phase 9 walk-forward populates atlas_v6_strategy_runs.

Usage
-----
    PYTHONPATH=. DATABASE_URL="$ATLAS_DB_URL" .venv/bin/python scripts/v6_optimize_weights.py

    # Optional: restrict IC estimation to a specific OOS window
    V6_OOS_START=2023-01-01 V6_OOS_END=2024-12-31 .venv/bin/python scripts/v6_optimize_weights.py

    # Dry run (no DB write):
    V6_DRY_RUN=1 .venv/bin/python scripts/v6_optimize_weights.py

Exit codes
----------
0 — success
1 — fatal (missing env, DB error)
2 — no winning candidate (all sims failed)
"""

from __future__ import annotations

import os
import sys
from datetime import date

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from atlas.trading.v6.composite import SignalWeights
from atlas.trading.v6.optimizer import (
    CandidateWeights,
    estimate_signal_ic_from_strategy_runs,
    generate_candidate_grid,
    persist_best_weights,
    rank_candidates,
)

log = structlog.get_logger()


def _parse_date_env(var: str) -> date | None:
    """Parse YYYY-MM-DD from env var; return None if unset."""
    val = os.environ.get(var)
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        log.warning("bad_date_env", var=var, value=val)
        return None


def main() -> int:
    db_url = os.environ.get("ATLAS_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        log.error("optimizer.no_db_url", hint="Set ATLAS_DB_URL or DATABASE_URL")
        return 1

    # Strip SQLAlchemy dialect prefix if passed raw psql URL
    # (SQLAlchemy dialect prefix fix: postgresql+psycopg2:// → postgresql://)
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)

    dry_run = bool(os.environ.get("V6_DRY_RUN", ""))

    oos_start = _parse_date_env("V6_OOS_START")
    oos_end = _parse_date_env("V6_OOS_END")
    oos_filter = (oos_start, oos_end) if oos_start and oos_end else None

    log.info("optimizer.start", dry_run=dry_run, oos_filter=str(oos_filter))

    try:
        eng = create_engine(db_url, pool_pre_ping=True)
        session = sessionmaker(bind=eng)()
    except Exception as exc:
        log.error("optimizer.db_connect_failed", error=str(exc))
        return 1

    # --- Step 1: Estimate per-signal IC from strategy runs ---
    try:
        observed = estimate_signal_ic_from_strategy_runs(session, oos_period_filter=oos_filter)
    except Exception as exc:
        log.error("optimizer.ic_estimation_failed", error=str(exc))
        return 1

    log.info("optimizer.observed_ic", **{k: round(v, 4) for k, v in observed.items()})

    # --- Step 2: Build prior and candidate grid ---
    prior = SignalWeights()
    candidates = generate_candidate_grid(observed, prior)
    log.info("optimizer.candidates_generated", n=len(candidates))

    # --- Step 3: Quick-eval on 2024 (most recent populated window) ---
    quick_window = (date(2024, 1, 1), date(2024, 12, 31))
    log.info("optimizer.quick_eval_window", start=str(quick_window[0]), end=str(quick_window[1]))

    try:
        ranked = rank_candidates(candidates, session, quick_window)
    except Exception as exc:
        log.error("optimizer.ranking_failed", error=str(exc))
        return 1

    if not ranked:
        log.error("optimizer.no_candidates_ranked")
        return 2

    # --- Step 4: Print ranking ---
    print("\n=== Candidate Ranking (by Calmar) ===")
    for i, (cand, stats) in enumerate(ranked):
        calmar = stats.get("calmar", 0.0)
        alpha_t = stats.get("alpha_t", 0.0)
        sharpe = stats.get("sharpe", 0.0)
        mdd = stats.get("mdd", 0.0)
        print(
            f"  #{i + 1}: lambda={cand.shrinkage_lambda:.2f}  "
            f"calmar={calmar:.2f}  alpha_t={alpha_t:.2f}  "
            f"sharpe={sharpe:.2f}  mdd={mdd:.1%}"
        )

    # --- Step 5: Select winner ---
    winner, winner_stats = ranked[0]

    # Guard: if winner calmar is sentinel -1.0, all sims failed
    if winner_stats.get("calmar", -1.0) < 0:
        log.error("optimizer.all_sims_failed", action="falling_back_to_pure_prior")
        # Fall back to pure prior (lambda=1.0)
        prior_candidate = CandidateWeights(
            weights=prior,
            expected_calmar=0.0,
            expected_alpha_t=0.0,
            shrinkage_lambda=1.0,
        )
        winner = prior_candidate

    print(f"\n=== Winner: lambda={winner.shrinkage_lambda:.2f} ===")
    print(f"  Calmar: {winner.expected_calmar:.3f}")
    print(f"  Alpha-t: {winner.expected_alpha_t:.3f}")
    print("\n  Signal weights:")
    for sig, w in winner.weights.as_dict().items():
        print(f"    {sig:25s}: {w:.4f}")

    if dry_run:
        print("\n[DRY RUN] Skipping atlas_signal_weights write.")
        log.info("optimizer.dry_run_complete")
        return 0

    # --- Step 6: Persist winner ---
    version = f"phase10_{date.today().isoformat()}"
    try:
        persist_best_weights(
            session=session,
            winner=winner,
            effective_from=date.today(),
            weight_set_version=version,
        )
    except Exception as exc:
        log.error("optimizer.persist_failed", error=str(exc))
        return 1

    print(f"\n=== Persisted: version='{version}', effective_from={date.today()} ===")
    log.info("optimizer.complete", version=version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
