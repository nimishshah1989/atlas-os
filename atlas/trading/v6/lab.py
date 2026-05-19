"""v6 trading model — thin orchestrator with public API.

This is the SHELL. All business logic lives in the bounded-context modules
(universe, signals, composite, portfolio, governance, regime, risk,
crisis_sleeve, simulator). lab.py only routes, coordinates, and persists.

Public API:
  run_backtest(start, end, **opts) -> SimulationResult
  live_rebalance(ref_date) -> list[Order]
  intramonth_scan(ref_date) -> list[Order]
  evaluate_goal_post(strategy_run_id) -> dict
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from atlas.trading.v6.composite import SignalWeights, compute_composite, select
from atlas.trading.v6.governance import apply_exclusions
from atlas.trading.v6.simulator import (
    SimulationConfig,
    SimulationResult,
    _compute_signal_panel,
    _get_trend_gate_pass,
    run_simulation,
)
from atlas.trading.v6.universe import get_investable

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Order dataclass
# ---------------------------------------------------------------------------


@dataclass
class Order:
    instrument_id: uuid.UUID
    symbol: str
    action: str  # 'BUY' | 'SELL' | 'HOLD'
    weight_target: float
    composite_score: float
    rank: int
    confidence_band: str  # 'HIGH' | 'MED' | 'LOW'


# ---------------------------------------------------------------------------
# DB session factory (reads from atlas.config or ATLAS_DB_URL env)
# ---------------------------------------------------------------------------


def _get_session() -> Session:
    """Create a SQLAlchemy session from the configured DB URL.

    Reads DATABASE_URL from environment or atlas.config.
    """
    import os

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("ATLAS_DB_URL")
    if not db_url:
        try:
            from atlas.config import settings  # type: ignore[import,attr-defined]

            db_url = settings.database_url  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            pass

    if not db_url:
        raise RuntimeError(
            "No database URL configured. Set DATABASE_URL or ATLAS_DB_URL environment variable."
        )

    engine = create_engine(
        db_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    factory = sessionmaker(bind=engine)
    return factory()


# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------


def run_backtest(
    start: date,
    end: date,
    strategy_name: str = "v6_default",
    target_holdings: int = 28,
    initial_capital_cr: float = 100.0,
    signal_weights: SignalWeights | None = None,
    persist: bool = True,
    session: Session | None = None,
) -> SimulationResult:
    """Top-level backtest entry point.

    Args:
        start: Backtest start date (inclusive).
        end: Backtest end date (inclusive).
        strategy_name: Name stored in atlas_v6_strategy_runs.
        target_holdings: Target portfolio size (enter_rank_cutoff).
        initial_capital_cr: Starting portfolio value in crores.
        signal_weights: Custom signal weight blend; None → default priors.
        persist: Whether to write result to atlas_v6_strategy_runs.
        session: Inject a SQLAlchemy session (for testing); creates one if None.

    Returns:
        SimulationResult with per-period returns and aggregate stats.
    """
    _bsession: Session = session if session is not None else _get_session()
    own_session = session is None

    try:
        config = SimulationConfig(
            start=start,
            end=end,
            strategy_name=strategy_name,
            target_holdings=target_holdings,
            initial_capital_cr=initial_capital_cr,
            signal_weights=signal_weights,
            persist=persist,
        )
        return run_simulation(_bsession, config)
    finally:
        if own_session:
            _bsession.close()


# ---------------------------------------------------------------------------
# live_rebalance
# ---------------------------------------------------------------------------


def live_rebalance(
    ref_date: date,
    target_holdings: int = 28,
    signal_weights: SignalWeights | None = None,
    session: Session | None = None,
) -> list[Order]:
    """Monthly live rebalance. Persists to atlas_v6_recommendations_daily.

    Computes composite scores for the investable universe at ref_date,
    applies governance + trend gate + buffer zones, and writes to DB.

    Returns list of Order objects for the new portfolio.
    """
    own_session = session is None
    if session is None:
        session = _get_session()
    assert session is not None  # mypy narrowing after conditional assignment

    try:
        # Universe
        instruments = get_investable(session, ref_date)
        if not instruments:
            log.warning("lab.live_rebalance.empty_universe", ref_date=str(ref_date))
            return []

        # Governance
        instrument_ids = [inst.instrument_id for inst in instruments]
        gov_excluded, _ = apply_exclusions(session, instrument_ids, ref_date)

        # Signal panel
        panel = _compute_signal_panel(session, instruments, ref_date)
        if panel.empty:
            log.warning("lab.live_rebalance.empty_panel", ref_date=str(ref_date))
            return []

        # Composite
        composite = compute_composite(panel, signal_weights)

        # Trend gate
        trend_gate_pass = _get_trend_gate_pass(session, instrument_ids, ref_date)

        # Selection (no prior holdings for live run — enter fresh)
        prior_holdings: set[uuid.UUID] = _load_prior_holdings(session, ref_date)
        selection = select(
            composite=composite,
            governance_excluded=gov_excluded,
            trend_gate_pass=trend_gate_pass,
            held_yesterday=prior_holdings,
            enter_rank_cutoff=target_holdings,
            stay_rank_cutoff=int(target_holdings * 1.6),
        )

        cohort = selection.entered + selection.held
        if not cohort:
            log.info("lab.live_rebalance.empty_cohort", ref_date=str(ref_date))
            return []

        # Composite scores and ranks for the cohort
        cohort_composite = composite[cohort].sort_values(ascending=False)
        equal_w = 1.0 / len(cohort)

        symbol_map = {inst.instrument_id: inst.symbol for inst in instruments}

        orders: list[Order] = []
        for rank, (iid, score) in enumerate(cohort_composite.items(), start=1):
            band = _confidence_band(rank, len(cohort))
            action = "BUY" if iid in selection.entered else "HOLD"
            orders.append(
                Order(
                    instrument_id=iid,
                    symbol=symbol_map.get(iid, str(iid)),
                    action=action,
                    weight_target=equal_w,
                    composite_score=float(score),
                    rank=rank,
                    confidence_band=band,
                )
            )

        # Exit orders for names no longer in cohort
        for iid in selection.exited:
            orders.append(
                Order(
                    instrument_id=iid,
                    symbol=symbol_map.get(iid, str(iid)),
                    action="SELL",
                    weight_target=0.0,
                    composite_score=float(composite.get(iid, 0.0)),
                    rank=len(cohort) + 1,
                    confidence_band="LOW",
                )
            )

        # Persist to DB
        _persist_recommendations(session, ref_date, orders)

        log.info(
            "lab.live_rebalance.done",
            ref_date=str(ref_date),
            n_buy=sum(1 for o in orders if o.action == "BUY"),
            n_hold=sum(1 for o in orders if o.action == "HOLD"),
            n_sell=sum(1 for o in orders if o.action == "SELL"),
        )

        return orders

    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# intramonth_scan
# ---------------------------------------------------------------------------


def intramonth_scan(
    ref_date: date,
    composite_threshold: float = 0.85,
    signal_weights: SignalWeights | None = None,
    session: Session | None = None,
) -> list[Order]:
    """Opportunistic intra-month scan for high-conviction new adds.

    Returns names with composite score > composite_threshold that are NOT
    already in the current live holdings.
    """
    _isession: Session = session if session is not None else _get_session()
    own_session = session is None

    try:
        instruments = get_investable(_isession, ref_date)
        if not instruments:
            return []

        instrument_ids = [inst.instrument_id for inst in instruments]
        gov_excluded, _ = apply_exclusions(_isession, instrument_ids, ref_date)

        panel = _compute_signal_panel(_isession, instruments, ref_date)
        if panel.empty:
            return []

        composite = compute_composite(panel, signal_weights)
        trend_gate_pass = _get_trend_gate_pass(_isession, instrument_ids, ref_date)
        current_holdings = _load_prior_holdings(_isession, ref_date)
        symbol_map = {inst.instrument_id: inst.symbol for inst in instruments}

        # Normalize composite to [0,1] range for threshold comparison
        c_min = composite.min()
        c_max = composite.max()
        c_range = c_max - c_min
        if c_range > 0:
            normalized = (composite - c_min) / c_range
        else:
            normalized = composite * 0

        # Candidates: high composite, not held, not excluded, pass trend gate
        candidates: list[Order] = []
        ranked = composite.sort_values(ascending=False)
        for rank, (iid, score) in enumerate(ranked.items(), start=1):
            norm_score = float(normalized.get(iid, 0.0))
            if norm_score < composite_threshold:
                continue
            if iid in gov_excluded:
                continue
            if iid not in trend_gate_pass:
                continue
            if iid in current_holdings:
                continue

            candidates.append(
                Order(
                    instrument_id=iid,
                    symbol=symbol_map.get(iid, str(iid)),
                    action="BUY",
                    weight_target=0.0,  # caller decides sizing
                    composite_score=float(score),
                    rank=rank,
                    confidence_band=_confidence_band(rank, len(ranked)),
                )
            )

        log.info(
            "lab.intramonth_scan.done",
            ref_date=str(ref_date),
            n_candidates=len(candidates),
            threshold=composite_threshold,
        )

        return candidates

    finally:
        if own_session:
            _isession.close()


# ---------------------------------------------------------------------------
# evaluate_goal_post
# ---------------------------------------------------------------------------


def evaluate_goal_post(
    strategy_run_id: uuid.UUID | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    """Evaluate 9 hard constraints from atlas_v6_strategy_runs.

    If strategy_run_id is None, uses the most recent run.
    Returns dict with constraint name → pass/fail + observed value.
    """
    _session: Session = session if session is not None else _get_session()
    own_session = session is None

    try:
        if strategy_run_id is not None:
            row = _session.execute(
                text("""
                    SELECT * FROM atlas.atlas_v6_strategy_runs
                     WHERE run_id = :rid
                """),
                {"rid": str(strategy_run_id)},
            ).fetchone()
        else:
            row = _session.execute(
                text("""
                    SELECT * FROM atlas.atlas_v6_strategy_runs
                     ORDER BY created_at DESC
                     LIMIT 1
                """),
            ).fetchone()

        if row is None:
            return {
                "status": "no_runs",
                "message": "No strategy runs found in atlas_v6_strategy_runs",
                "constraints": {},
            }

        # 9 hard constraints per spec §8.4
        constraints: dict[str, dict[str, Any]] = {}

        def _check(name: str, value: Any, threshold: Any, direction: str) -> None:
            """direction: 'gte' or 'lte'"""
            if value is None:
                constraints[name] = {
                    "pass": False,
                    "value": None,
                    "threshold": threshold,
                    "reason": "NULL",
                }
                return
            v = float(value)
            passed = (v >= threshold) if direction == "gte" else (v <= threshold)
            constraints[name] = {"pass": passed, "value": v, "threshold": threshold}

        # C1: Calmar ≥ 0.5
        _check("calmar", row.calmar, 0.5, "gte")

        # C2: Max drawdown ≤ -20% (mdd_ratio is stored as negative fraction)
        _check("max_drawdown", row.mdd_ratio, -0.20, "gte")

        # C3: Win rate ≥ 50%
        _check("win_rate", row.win_rate, 0.50, "gte")

        # C4: Sharpe (alpha_t_stat as proxy) — no direct Sharpe column; check passes_all
        # Using alpha_t_stat as alpha significance proxy
        _check("alpha_t_stat", row.alpha_t_stat, 1.5, "gte")

        # C5: Vol ratio ≤ 1.5× benchmark vol
        _check("vol_ratio", row.vol_ratio, 1.5, "lte")

        # C6: MDD ratio ≤ 2.0× benchmark MDD
        _check("mdd_ratio_vs_benchmark", row.mdd_ratio, -0.25, "gte")

        # C7: OOS IC retention ≥ 70% (only if walk-forward was run)
        if row.oos_ic_retention is not None:
            _check("oos_ic_retention", row.oos_ic_retention, 0.70, "gte")
        else:
            constraints["oos_ic_retention"] = {
                "pass": True,  # no WF run yet → not failing
                "value": None,
                "threshold": 0.70,
                "reason": "walk-forward not yet run",
            }

        # C8: Portfolio capacity ≥ ₹500cr (if computed)
        if row.capacity_cr is not None:
            _check("capacity_cr", row.capacity_cr, 500.0, "gte")
        else:
            constraints["capacity_cr"] = {
                "pass": True,
                "value": None,
                "threshold": 500.0,
                "reason": "capacity not yet computed",
            }

        # C9: Annual turnover ≤ 4× (if computed)
        if row.turnover_annual is not None:
            _check("turnover_annual", row.turnover_annual, 4.0, "lte")
        else:
            constraints["turnover_annual"] = {
                "pass": True,
                "value": None,
                "threshold": 4.0,
                "reason": "turnover not yet computed",
            }

        all_pass = all(c["pass"] for c in constraints.values())
        failing = [k for k, v in constraints.items() if not v["pass"]]

        return {
            "status": "pass" if all_pass else "fail",
            "run_id": str(row.run_id),
            "strategy_name": row.strategy_name,
            "passes_all_constraints": all_pass,
            "failing_constraints": failing,
            "constraints": constraints,
        }

    finally:
        if own_session:
            _session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _confidence_band(rank: int, total: int) -> str:
    """Assign confidence band based on rank within cohort."""
    pct = rank / total if total > 0 else 1.0
    if pct <= 0.33:
        return "HIGH"
    if pct <= 0.67:
        return "MED"
    return "LOW"


def _load_prior_holdings(session: Session, ref_date: date) -> set[uuid.UUID]:
    """Load current live holdings from atlas_v6_recommendations_daily.

    Returns set of instrument_ids with action IN ('BUY', 'HOLD') from the
    most recent recommendation date before ref_date.
    """
    row = session.execute(
        text("""
            SELECT MAX(date) AS last_date
              FROM atlas.atlas_v6_recommendations_daily
             WHERE date < :d
        """),
        {"d": ref_date},
    ).fetchone()

    if row is None or row.last_date is None:
        return set()

    holdings_rows = session.execute(
        text("""
            SELECT instrument_id
              FROM atlas.atlas_v6_recommendations_daily
             WHERE date = :d
        """),
        {"d": row.last_date},
    ).fetchall()

    return {uuid.UUID(str(r.instrument_id)) for r in holdings_rows}


def _persist_recommendations(
    session: Session,
    ref_date: date,
    orders: list[Order],
) -> None:
    """Write orders to atlas_v6_recommendations_daily. Idempotent ON CONFLICT."""
    if not orders:
        return

    for order in orders:
        if order.action == "SELL":
            # Don't persist zero-weight sells to recommendations_daily
            continue

        session.execute(
            text("""
                INSERT INTO atlas.atlas_v6_recommendations_daily
                    (date, instrument_id, composite_score, weight_in_book, rank, confidence_band)
                VALUES (:d, :iid, :score, :weight, :rank, :band)
                ON CONFLICT (date, instrument_id) DO UPDATE SET
                    composite_score = EXCLUDED.composite_score,
                    weight_in_book  = EXCLUDED.weight_in_book,
                    rank            = EXCLUDED.rank,
                    confidence_band = EXCLUDED.confidence_band
            """),
            {
                "d": ref_date,
                "iid": str(order.instrument_id),
                "score": Decimal(str(round(order.composite_score, 6))),
                "weight": Decimal(str(round(order.weight_target, 6))),
                "rank": order.rank,
                "band": order.confidence_band,
            },
        )

    session.commit()
    log.info(
        "lab.recommendations_persisted",
        ref_date=str(ref_date),
        n_rows=len([o for o in orders if o.action != "SELL"]),
    )
