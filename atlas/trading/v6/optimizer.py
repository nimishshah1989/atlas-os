"""atlas.trading.v6.optimizer — Bayesian shrinkage weight optimization.

Plan 2 Phase 10. Spec §6.2.

Public API
----------
estimate_signal_ic_from_strategy_runs  — extract per-signal IC proxy from DB
bayesian_shrinkage_weights             — (1-λ)×observed + λ×prior blend
generate_candidate_grid                — 7-lambda candidate set
rank_candidates                        — quick-eval each candidate via simulator
persist_best_weights                   — write winner to atlas_signal_weights

Design decisions
----------------
- atlas_v6_strategy_runs has no per-signal IC column. IC is proxied as a
  weighted contribution: for each run, weight_i × calmar contributes to
  signal_i's estimated predictive value. Normalized across runs.
- Decimal at DB boundary. float internally (optimizer math).
- rank_candidates runs simulator with persist=False to avoid polluting
  atlas_v6_strategy_runs with optimization noise.
- persist_best_weights uses tier='tier_1_megacap' + approved_by field to
  distinguish v6 rows from SP04 rows (avoids a new migration; the CHECK
  constraint on tier only allows tier_1..tier_5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from atlas.trading.v6.composite import SignalWeights

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

_SIGNALS = list(SignalWeights.__dataclass_fields__.keys())  # type: ignore[attr-defined]

_V6_TIER = "tier_1_megacap"  # sentinel tier for v6 optimizer rows
_V6_REGIME = "all"


@dataclass(frozen=True)
class CandidateWeights:
    """One candidate weight set with expected performance estimates."""

    weights: SignalWeights
    expected_calmar: float
    expected_alpha_t: float
    shrinkage_lambda: float  # how much pull toward prior (0 = pure data, 1 = pure prior)


# ---------------------------------------------------------------------------
# IC estimation
# ---------------------------------------------------------------------------


def estimate_signal_ic_from_strategy_runs(
    session: Session,
    oos_period_filter: tuple[date, date] | None = None,
) -> dict[str, float]:
    """Read atlas_v6_strategy_runs; derive per-signal IC proxy from calmar × weight.

    Algorithm
    ---------
    For each strategy run:
      - Extract signal_weights JSONB dict
      - Multiply each weight_i by run.calmar (clip floor 0) → contribution_i
    Aggregate across runs: IC_proxy_i = sum(contribution_i) / n_runs

    If no runs exist or all calmar = 0, returns uniform IC (equal across signals).
    OOS filter: restricts to runs where is_period overlaps the given date range.

    Parameters
    ----------
    session : sqlalchemy Session
    oos_period_filter : optional (start_date, end_date) to filter on is_period

    Returns
    -------
    dict[str, float]  — per-signal IC proxy, NOT normalized (caller normalizes)
    """
    if oos_period_filter is not None:
        start, end = oos_period_filter
        sql = text("""
            SELECT signal_weights, calmar
            FROM atlas.atlas_v6_strategy_runs
            WHERE calmar IS NOT NULL
              AND is_period && tsrange(:start::date::timestamp,
                                      :end::date::timestamp, '[]')
        """)
        params: dict = {"start": str(start), "end": str(end)}
    else:
        sql = text("""
            SELECT signal_weights, calmar
            FROM atlas.atlas_v6_strategy_runs
            WHERE calmar IS NOT NULL
        """)
        params = {}

    rows = session.execute(sql, params).fetchall()
    n_rows = len(rows)
    log.info("optimizer.ic_query", n_rows=n_rows, oos_filter=str(oos_period_filter))

    if n_rows == 0:
        log.warning("optimizer.no_runs_found", action="using_uniform_ic")
        return {s: 1.0 for s in _SIGNALS}

    # Accumulate contribution per signal
    accum: dict[str, float] = {s: 0.0 for s in _SIGNALS}
    valid_rows = 0

    for row in rows:
        weights_raw = row[0]
        calmar_raw = row[1]

        # Parse JSONB — may come back as str or dict depending on driver
        if isinstance(weights_raw, str):
            try:
                weights_dict: dict = json.loads(weights_raw)
            except (json.JSONDecodeError, TypeError):
                log.warning("optimizer.invalid_weights_json", row=str(row))
                continue
        elif isinstance(weights_raw, dict):
            weights_dict = weights_raw
        else:
            log.warning("optimizer.unexpected_weights_type", type=type(weights_raw).__name__)
            continue

        calmar = float(calmar_raw) if calmar_raw is not None else 0.0
        # Clip calmar floor at 0 — negative calmar gives negative IC proxy
        calmar_clipped = max(0.0, calmar)

        for sig in _SIGNALS:
            w = float(weights_dict.get(sig, 0.0))
            accum[sig] += w * calmar_clipped

        valid_rows += 1

    if valid_rows == 0:
        log.warning("optimizer.all_rows_invalid", action="using_uniform_ic")
        return {s: 1.0 for s in _SIGNALS}

    # If all accum values are 0 (all calmar=0), return uniform
    total_accum = sum(accum.values())
    if total_accum == 0.0:
        log.warning("optimizer.all_calmar_zero", action="using_uniform_ic")
        return {s: 1.0 for s in _SIGNALS}

    log.info(
        "optimizer.ic_estimated",
        valid_rows=valid_rows,
        **{k: round(v, 4) for k, v in accum.items()},
    )
    return accum


# ---------------------------------------------------------------------------
# Bayesian shrinkage
# ---------------------------------------------------------------------------


def bayesian_shrinkage_weights(
    observed_ic: dict[str, float],
    prior_weights: SignalWeights,
    shrinkage_lambda: float = 0.15,
) -> SignalWeights:
    """Blend observed IC with prior weights via Bayesian shrinkage (spec §6.2).

    Formula
    -------
        signal_weight_i = (1 - lambda) × normalize(observed_ic_i)
                        + lambda × normalize(prior_weight_i)

    where normalize maps a dict to sum-to-1 proportional weights.

    Parameters
    ----------
    observed_ic : dict mapping signal_name → IC proxy value (non-negative floats)
    prior_weights : SignalWeights — informative priors
    shrinkage_lambda : float in [0, 1] — 0 = pure data, 1 = pure prior

    Returns
    -------
    SignalWeights — new weight set
    """
    if not 0.0 <= shrinkage_lambda <= 1.0:
        raise ValueError(f"shrinkage_lambda must be in [0, 1], got {shrinkage_lambda}")

    prior_dict = prior_weights.as_dict()

    # Normalize observed IC — guard zero total
    ic_total = sum(max(0.0, observed_ic.get(s, 0.0)) for s in _SIGNALS)
    if ic_total == 0.0:
        # Degenerate: fall back to pure prior
        log.warning("optimizer.zero_ic_total", action="falling_back_to_prior")
        ic_normalized = {s: prior_dict[s] / sum(prior_dict.values()) for s in _SIGNALS}
    else:
        ic_normalized = {s: max(0.0, observed_ic.get(s, 0.0)) / ic_total for s in _SIGNALS}

    # Normalize prior
    prior_total = sum(prior_dict.values())
    if prior_total == 0.0:
        raise ValueError("prior_weights sum to zero — cannot normalize")
    prior_normalized = {s: prior_dict[s] / prior_total for s in _SIGNALS}

    # Blend
    blended = {
        s: (1.0 - shrinkage_lambda) * ic_normalized[s] + shrinkage_lambda * prior_normalized[s]
        for s in _SIGNALS
    }

    # Verify normalization (should sum to 1.0 by construction)
    blend_total = sum(blended.values())
    assert abs(blend_total - 1.0) < 1e-9, f"Blended weights sum to {blend_total}, expected 1.0"

    # Scale back to match prior total (so weights stay in comparable range)
    # Prior sums to ~0.99; scale blended by that same factor
    scaled = {s: blended[s] * prior_total for s in _SIGNALS}

    return SignalWeights(**scaled)


# ---------------------------------------------------------------------------
# Candidate grid
# ---------------------------------------------------------------------------

_DEFAULT_LAMBDAS: list[float] = [0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 1.00]


def generate_candidate_grid(
    observed_ic: dict[str, float],
    prior_weights: SignalWeights,
    lambdas: list[float] = _DEFAULT_LAMBDAS,
) -> list[CandidateWeights]:
    """Generate one CandidateWeights per lambda value.

    Parameters
    ----------
    observed_ic : per-signal IC proxy (output of estimate_signal_ic_from_strategy_runs)
    prior_weights : SignalWeights priors
    lambdas : list of shrinkage lambdas to try

    Returns
    -------
    list[CandidateWeights] — one per lambda, len == len(lambdas)
    """
    if not lambdas:
        raise ValueError("lambdas list cannot be empty")

    candidates: list[CandidateWeights] = []
    for lam in lambdas:
        weights = bayesian_shrinkage_weights(observed_ic, prior_weights, shrinkage_lambda=lam)
        candidates.append(
            CandidateWeights(
                weights=weights,
                expected_calmar=0.0,  # filled by rank_candidates
                expected_alpha_t=0.0,  # filled by rank_candidates
                shrinkage_lambda=lam,
            )
        )

    log.info("optimizer.candidates_generated", n=len(candidates), lambdas=lambdas)
    return candidates


# ---------------------------------------------------------------------------
# Rank candidates via quick simulation
# ---------------------------------------------------------------------------


def rank_candidates(
    candidates: list[CandidateWeights],
    session: Session,
    quick_eval_window: tuple[date, date],
) -> list[tuple[CandidateWeights, dict]]:
    """Run a quick simulation for each candidate on quick_eval_window.

    Ranks by Calmar descending. Candidates that fail simulation are penalized
    (calmar = -1) but kept so the caller always gets len(candidates) results.

    Parameters
    ----------
    candidates : list from generate_candidate_grid
    session : sqlalchemy Session
    quick_eval_window : (start, end) dates for simulation

    Returns
    -------
    list of (CandidateWeights_with_filled_metrics, stats_dict)
    sorted by calmar descending (best first)
    """
    # Import here to avoid circular at module load (simulator imports composite)
    from atlas.trading.v6.simulator import SimulationConfig, run_simulation

    start, end = quick_eval_window
    results: list[tuple[CandidateWeights, dict]] = []

    for i, cand in enumerate(candidates):
        config = SimulationConfig(
            start=start,
            end=end,
            signal_weights=cand.weights,
            strategy_name=f"optimizer_lambda_{cand.shrinkage_lambda:.2f}",
            persist=False,  # do NOT write to atlas_v6_strategy_runs
        )
        try:
            sim = run_simulation(session, config)
            stats = {
                "calmar": sim.calmar,
                "alpha_t": sim.alpha_t_stat,
                "sharpe": sim.sharpe,
                "mdd": sim.max_drawdown,
                "ann_return": sim.ann_return,
            }
            filled = CandidateWeights(
                weights=cand.weights,
                expected_calmar=sim.calmar,
                expected_alpha_t=sim.alpha_t_stat,
                shrinkage_lambda=cand.shrinkage_lambda,
            )
            log.info(
                "optimizer.candidate_eval",
                rank_idx=i,
                lam=cand.shrinkage_lambda,
                calmar=round(sim.calmar, 3),
                alpha_t=round(sim.alpha_t_stat, 3),
            )
        except Exception as exc:
            log.warning(
                "optimizer.candidate_eval_failed",
                lam=cand.shrinkage_lambda,
                error=str(exc),
            )
            stats = {"calmar": -1.0, "alpha_t": 0.0, "sharpe": 0.0, "mdd": 0.0, "ann_return": 0.0}
            filled = CandidateWeights(
                weights=cand.weights,
                expected_calmar=-1.0,
                expected_alpha_t=0.0,
                shrinkage_lambda=cand.shrinkage_lambda,
            )

        results.append((filled, stats))

    # Sort by calmar descending
    results.sort(key=lambda x: x[1].get("calmar", -1.0), reverse=True)
    log.info(
        "optimizer.ranking_done",
        n=len(results),
        best_lambda=results[0][0].shrinkage_lambda if results else None,
        best_calmar=round(results[0][1].get("calmar", 0.0), 3) if results else None,
    )
    return results


# ---------------------------------------------------------------------------
# Persist winner
# ---------------------------------------------------------------------------


def persist_best_weights(
    session: Session,
    winner: CandidateWeights,
    effective_from: date,
    weight_set_version: str,
) -> None:
    """Write winner weights to atlas_signal_weights.

    Schema notes (migration 039)
    ----------------------------
    - tier CHECK constraint: tier_1_megacap..tier_5_smallcap only.
      v6 rows use tier='tier_1_megacap' with regime='all' and
      approved_by=weight_set_version as distinguishing fields.
    - Idempotent: closes prior v6 active rows (effective_to = effective_from - 1)
      then inserts new rows. ON CONFLICT on partial unique index
      (tier, regime, signal_name) WHERE effective_to IS NULL.

    Parameters
    ----------
    session : sqlalchemy Session
    winner : CandidateWeights — best candidate from rank_candidates
    effective_from : date — when these weights take effect
    weight_set_version : str — identifier stored in approved_by, e.g. 'phase10_2026-01-01'
    """
    weights_dict = winner.weights.as_dict()
    now = datetime.now(tz=UTC)

    # Step 1: Close currently-active v6 rows by setting effective_to
    close_sql = text("""
        UPDATE atlas.atlas_signal_weights
        SET effective_to = :eff_from - INTERVAL '1 day',
            updated_at   = :now
        WHERE tier       = :tier
          AND regime     = :regime
          AND approved_by LIKE 'phase10_%'
          AND effective_to IS NULL
    """)
    closed = session.execute(
        close_sql,
        {
            "eff_from": effective_from,
            "now": now,
            "tier": _V6_TIER,
            "regime": _V6_REGIME,
        },
    )
    log.info("optimizer.closed_prior_rows", count=closed.rowcount)

    # Step 2: Insert new rows, one per signal
    insert_sql = text("""
        INSERT INTO atlas.atlas_signal_weights (
            tier, regime, signal_name, weight,
            effective_from, effective_to,
            approved_by, approved_at,
            notes, created_at, updated_at
        ) VALUES (
            :tier, :regime, :signal_name, :weight,
            :effective_from, NULL,
            :approved_by, :approved_at,
            :notes, :now, :now
        )
        ON CONFLICT (tier, regime, signal_name)
        WHERE effective_to IS NULL
        DO UPDATE SET
            weight       = EXCLUDED.weight,
            effective_from = EXCLUDED.effective_from,
            approved_by  = EXCLUDED.approved_by,
            approved_at  = EXCLUDED.approved_at,
            notes        = EXCLUDED.notes,
            updated_at   = EXCLUDED.updated_at
    """)

    n_inserted = 0
    for signal_name, weight_float in weights_dict.items():
        weight_decimal = Decimal(str(round(weight_float, 6)))
        session.execute(
            insert_sql,
            {
                "tier": _V6_TIER,
                "regime": _V6_REGIME,
                "signal_name": signal_name,
                "weight": weight_decimal,
                "effective_from": effective_from,
                "approved_by": weight_set_version,
                "approved_at": now,
                "notes": (
                    f"v6 Phase 10 optimizer | lambda={winner.shrinkage_lambda:.2f} | "
                    f"calmar={winner.expected_calmar:.3f} | "
                    f"alpha_t={winner.expected_alpha_t:.3f}"
                ),
                "now": now,
            },
        )
        n_inserted += 1

    session.commit()

    log.info(
        "optimizer.weights_persisted",
        n_signals=n_inserted,
        effective_from=str(effective_from),
        weight_set_version=weight_set_version,
        lambda_used=winner.shrinkage_lambda,
    )
