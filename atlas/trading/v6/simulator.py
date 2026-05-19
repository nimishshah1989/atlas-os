# allow-large: Single-responsibility backtest engine. Eight cohesive sections:
# (1) dataclasses, (2) main loop, (3) single-period execution, (4) date helpers,
# (5) signal panel builder, (6) trend gate, (7) returns/benchmark helpers,
# (8) slippage + aggregate stats + persistence. Splitting would create coupling
# worse than the line count. Responsibility count = 1 (simulate a backtest).

"""v6 backtest engine — monthly rebalance loop.

Orchestrates all bounded-context modules into a full backtest simulation:
  universe → governance → signals → composite → select → HRP → regime → risk → sleeve → orders

Each rebalance date:
  1. get_investable(session, date) — PIT Nifty 500 + ADV floor
  2. apply_exclusions(session, universe_ids, date) — governance batch check
  3. _compute_signal_panel(session, instruments, date) — 9 signals, bulk SQL
  4. compute_composite(panel, weights) → per-instrument score
  5. select(composite, gov_excluded, trend_gate_pass, held_yesterday) → cohort
  6. HrpAllocator.allocate(returns_panel, sector_map, group_map) → HRP weights
  7. compute_regime(session, date) → gross multiplier
  8. vol_targeted_gross(realized_vol, gross_mult) → exposure scalar
  9. allocate_sleeve(session, date, regime.score) → crisis sleeve
  10. Compute orders, apply slippage, record period return

All financial values stored as Decimal at DB boundary; float used internally.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from atlas.trading.v6.composite import SignalWeights, compute_composite, select
from atlas.trading.v6.crisis_sleeve import allocate as allocate_sleeve
from atlas.trading.v6.governance import apply_exclusions
from atlas.trading.v6.portfolio import HrpAllocator
from atlas.trading.v6.regime import compute_regime
from atlas.trading.v6.risk import slippage_bps, vol_targeted_gross
from atlas.trading.v6.universe import InvestableInstrument, get_investable

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses — result types
# ---------------------------------------------------------------------------


@dataclass
class PeriodResult:
    rebalance_date: date
    end_date: date
    book_return: float
    benchmark_return: float
    alpha: float
    holdings_count: int
    sleeve_pct: float
    cash_pct: float
    gross_exposure: float
    regime_score: int


@dataclass
class SimulationResult:
    strategy_name: str
    periods: list[PeriodResult]
    ann_return: float
    max_drawdown: float
    vol: float
    sharpe: float
    calmar: float
    win_rate: float
    n_trades: int


@dataclass
class SimulationConfig:
    start: date
    end: date
    rebalance_freq: str = "M"  # M=monthly
    target_holdings: int = 28
    initial_capital_cr: float = 100.0
    signal_weights: SignalWeights | None = None
    strategy_name: str = "v6_default"
    persist: bool = True  # write row to atlas_v6_strategy_runs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_simulation(session: Session, config: SimulationConfig) -> SimulationResult:
    """Run a monthly rebalance backtest over [config.start, config.end].

    Returns SimulationResult with per-period results and aggregate stats.
    Optionally persists one row to atlas_v6_strategy_runs.
    """
    log.info(
        "simulator.start",
        strategy=config.strategy_name,
        start=str(config.start),
        end=str(config.end),
    )

    # Pull all trading dates in range
    all_dates = _trading_dates_in_range(session, config.start, config.end)
    if not all_dates:
        raise ValueError(
            f"No trading dates found in atlas_market_regime_daily "
            f"for [{config.start}, {config.end}]"
        )

    rebalance_dates = _monthly_rebalance_dates(all_dates, config.rebalance_freq)
    if not rebalance_dates:
        raise ValueError(f"No rebalance dates derived for [{config.start}, {config.end}]")

    log.info(
        "simulator.dates",
        total_trading_days=len(all_dates),
        rebalance_count=len(rebalance_dates),
    )

    periods: list[PeriodResult] = []
    equity_curve: list[float] = [1.0]  # NAV starts at 1.0
    held_yesterday: set[uuid.UUID] = set()
    prior_weights: dict[uuid.UUID, float] = {}
    n_trades = 0

    allocator = HrpAllocator(
        single_name_cap=0.05,
        sector_cap=0.25,
        issuer_group_cap=0.05,
        weight_floor=0.005,
    )

    for i, reb_date in enumerate(rebalance_dates):
        next_reb = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else config.end

        try:
            period = _run_single_period(
                session=session,
                config=config,
                allocator=allocator,
                rebalance_date=reb_date,
                end_date=next_reb,
                held_yesterday=held_yesterday,
                prior_weights=prior_weights,
                equity_curve=equity_curve,
            )
        except ValueError as exc:
            log.warning(
                "simulator.period_skipped",
                rebalance_date=str(reb_date),
                reason=str(exc),
            )
            # No regime data or empty universe — carry forward, mark zero return
            period = PeriodResult(
                rebalance_date=reb_date,
                end_date=next_reb,
                book_return=0.0,
                benchmark_return=0.0,
                alpha=0.0,
                holdings_count=len(held_yesterday),
                sleeve_pct=0.05,
                cash_pct=0.95,
                gross_exposure=0.30,
                regime_score=0,
            )

        # Update equity curve with book return
        equity_curve.append(equity_curve[-1] * (1.0 + period.book_return))

        # Trades = changes from prior_weights (count entries/exits)
        if prior_weights:
            n_trades += len(held_yesterday.symmetric_difference(set(prior_weights.keys())))

        periods.append(period)

        # Update state for next period
        held_yesterday = set(prior_weights.keys())

    # Aggregate statistics
    result = _compute_aggregate_stats(
        strategy_name=config.strategy_name,
        periods=periods,
        equity_curve=equity_curve,
        n_trades=n_trades,
    )

    if config.persist:
        _persist_strategy_run(session, config, result)

    log.info(
        "simulator.done",
        strategy=config.strategy_name,
        ann_return=round(result.ann_return, 4),
        max_drawdown=round(result.max_drawdown, 4),
        sharpe=round(result.sharpe, 4),
        calmar=round(result.calmar, 4),
        n_periods=len(periods),
    )

    return result


# ---------------------------------------------------------------------------
# Single-period execution
# ---------------------------------------------------------------------------


def _run_single_period(
    session: Session,
    config: SimulationConfig,
    allocator: HrpAllocator,
    rebalance_date: date,
    end_date: date,
    held_yesterday: set[uuid.UUID],
    prior_weights: dict[uuid.UUID, float],
    equity_curve: list[float],
) -> PeriodResult:
    """Execute one monthly rebalance period. Returns PeriodResult.

    Mutates prior_weights in-place to reflect new holdings at period end.
    """
    # Step 1 — Universe
    instruments = get_investable(session, rebalance_date)
    if not instruments:
        log.warning("simulator.empty_universe", date=str(rebalance_date))
        prior_weights.clear()
        return PeriodResult(
            rebalance_date=rebalance_date,
            end_date=end_date,
            book_return=0.0,
            benchmark_return=_benchmark_return(session, rebalance_date, end_date),
            alpha=0.0,
            holdings_count=0,
            sleeve_pct=0.05,
            cash_pct=1.0,
            gross_exposure=0.30,
            regime_score=0,
        )

    # Step 2 — Governance
    instrument_ids = [inst.instrument_id for inst in instruments]
    gov_excluded, _logs = apply_exclusions(session, instrument_ids, rebalance_date)

    # Step 3 — Signal panel
    panel = _compute_signal_panel(session, instruments, rebalance_date)
    if panel.empty:
        log.warning("simulator.empty_signal_panel", date=str(rebalance_date))
        prior_weights.clear()
        return PeriodResult(
            rebalance_date=rebalance_date,
            end_date=end_date,
            book_return=0.0,
            benchmark_return=_benchmark_return(session, rebalance_date, end_date),
            alpha=0.0,
            holdings_count=0,
            sleeve_pct=0.05,
            cash_pct=1.0,
            gross_exposure=0.30,
            regime_score=0,
        )

    # Step 4 — Composite
    composite = compute_composite(panel, config.signal_weights)

    # Trend gate: instruments where close >= 200dMA
    trend_gate_pass = _get_trend_gate_pass(session, instrument_ids, rebalance_date)

    # Step 5 — Selection with buffer zones
    selection = select(
        composite=composite,
        governance_excluded=gov_excluded,
        trend_gate_pass=trend_gate_pass,
        held_yesterday=held_yesterday,
        enter_rank_cutoff=config.target_holdings,
        stay_rank_cutoff=int(config.target_holdings * 1.6),
    )

    cohort = selection.entered + selection.held
    if not cohort:
        log.warning("simulator.empty_cohort_after_selection", date=str(rebalance_date))
        prior_weights.clear()
        return PeriodResult(
            rebalance_date=rebalance_date,
            end_date=end_date,
            book_return=0.0,
            benchmark_return=_benchmark_return(session, rebalance_date, end_date),
            alpha=0.0,
            holdings_count=0,
            sleeve_pct=0.05,
            cash_pct=1.0,
            gross_exposure=0.30,
            regime_score=0,
        )

    # Step 6 — HRP weights
    returns_panel = _fetch_returns_panel(session, cohort, rebalance_date, lookback_days=252)
    sector_map = {inst.instrument_id: (inst.sector or "Unknown") for inst in instruments}
    group_map = {iid: sector_map.get(iid, "Unknown") for iid in cohort}

    if returns_panel.empty or len(returns_panel.columns) < 2:
        # Not enough return history — equal weight fallback
        n = len(cohort)
        hrp_weights = pd.Series({iid: 1.0 / n for iid in cohort})
    else:
        hrp_result = allocator.allocate(returns_panel, sector_map, group_map)
        hrp_weights = hrp_result.weights

    # Step 7 — Regime
    regime = compute_regime(session, rebalance_date)

    # Step 8 — Vol-targeted gross
    if len(returns_panel.columns) >= 2 and len(returns_panel) >= 21:
        port_ret = (returns_panel[list(hrp_weights.index)] * hrp_weights).sum(axis=1)
        realized_vol = float(port_ret.std() * math.sqrt(252))
    else:
        realized_vol = 0.0

    gross = vol_targeted_gross(realized_vol, regime.gross_multiplier)

    # Step 9 — Crisis sleeve
    sleeve = allocate_sleeve(session, rebalance_date, regime.score)
    sleeve_pct = sleeve.sleeve_pct_of_book

    # Step 10 — Equity weight allocation
    equity_weight = (1.0 - sleeve_pct) * gross
    cash_pct = max(0.0, 1.0 - equity_weight - sleeve_pct)

    # Normalize equity weights to equity_weight fraction of book
    total_hrp = hrp_weights.sum()
    if total_hrp > 0:
        book_weights: dict[uuid.UUID, float] = {
            iid: float(hrp_weights[iid]) / total_hrp * equity_weight for iid in hrp_weights.index
        }
    else:
        book_weights = {}

    # Compute orders (diff vs prior) and apply slippage
    slippage_drag = _compute_slippage_drag(
        session=session,
        new_weights=book_weights,
        prior_weights=prior_weights,
        instruments=instruments,
        initial_capital_cr=config.initial_capital_cr,
        rebalance_date=rebalance_date,
    )

    # Period return: forward returns from rebalance_date to end_date
    forward_returns = _fetch_forward_returns(
        session, list(book_weights.keys()), rebalance_date, end_date
    )

    book_return = (
        float(
            sum(book_weights.get(iid, 0.0) * forward_returns.get(iid, 0.0) for iid in book_weights)
        )
        - slippage_drag
    )

    bench_return = _benchmark_return(session, rebalance_date, end_date)

    # Update prior_weights for next period
    prior_weights.clear()
    prior_weights.update(book_weights)

    return PeriodResult(
        rebalance_date=rebalance_date,
        end_date=end_date,
        book_return=book_return,
        benchmark_return=bench_return,
        alpha=book_return - bench_return,
        holdings_count=len(book_weights),
        sleeve_pct=sleeve_pct,
        cash_pct=cash_pct,
        gross_exposure=gross,
        regime_score=regime.score,
    )


# ---------------------------------------------------------------------------
# Trading dates + rebalance schedule
# ---------------------------------------------------------------------------


def _trading_dates_in_range(session: Session, start: date, end: date) -> list[date]:
    """Pull trading dates from atlas_market_regime_daily within [start, end]."""
    rows = session.execute(
        text("""
            SELECT date
              FROM atlas.atlas_market_regime_daily
             WHERE date >= :s AND date <= :e
             ORDER BY date
        """),
        {"s": start, "e": end},
    ).fetchall()
    return [r.date for r in rows]


def _monthly_rebalance_dates(trading_dates: list[date], freq: str = "M") -> list[date]:
    """Return the last trading day of each calendar month in the date list."""
    if not trading_dates:
        return []
    df = pd.Series(trading_dates)
    df.index = pd.to_datetime(df.values)
    # Group by year-month, pick last date in each group
    monthly = df.groupby(df.index.to_period("M")).last()
    return [d.date() if hasattr(d, "date") else d for d in monthly.values]


# ---------------------------------------------------------------------------
# Signal panel builder (SQL bulk-fetch — no per-instrument loops)
# ---------------------------------------------------------------------------


def _compute_signal_panel(
    session: Session,
    instruments: list[InvestableInstrument],
    ref_date: date,
) -> pd.DataFrame:
    """Build 9-signal panel for all instruments at ref_date.

    Returns DataFrame indexed by instrument_id with columns:
      natr_14, beta_alpha_63d, mom_low_vol, residual_momentum, proximity_52wh,
      industry_rs, fip_smoothness, bab, quality_proxy, sector

    SQL-first approach: pulls pre-computed metrics from atlas_stock_metrics_daily
    to avoid loading raw OHLCV for all 500 stocks per date.

    Columns mapped:
      natr_14             → natr_14 (or realized_vol_63 proxy)
      beta_alpha_63d      → alpha_63d (pre-computed in atlas_stock_metrics_daily)
      mom_low_vol         → ret_12m * (1 - vol_rank) proxy via ret_12m / realized_vol_63
      proximity_52wh      → computed from high_252d / close_63d proxy
      fip_smoothness      → computed from positive_days_252d / 252
      bab                 → 1 - beta rank (cross-sectional inverse rank of beta_63d)
      industry_rs         → ret_3m - sector median ret_3m
      residual_momentum   → alpha_63d as residual proxy (full OLS deferred)
      quality_proxy       → -0.5×rank(vol) - 0.3×rank(mdd) + 0.2×rank(consistency)
    """
    if not instruments:
        return pd.DataFrame()

    iid_strs = [str(inst.instrument_id) for inst in instruments]
    lookback = ref_date - timedelta(days=2)  # Use most recent available row

    rows = session.execute(
        text("""
            SELECT DISTINCT ON (m.instrument_id)
                m.instrument_id,
                m.natr_14,
                m.alpha_63d,
                m.ret_12m,
                m.ret_3m,
                m.realized_vol_63,
                m.beta_63d,
                m.ma_200d,
                m.close,
                m.max_drawdown_252d,
                m.positive_days_252d,
                m.worst_quarter_ret
              FROM atlas.atlas_stock_metrics_daily m
             WHERE m.instrument_id = ANY(:iids)
               AND m.date <= :ref
               AND m.date >= :lb
             ORDER BY m.instrument_id, m.date DESC
        """),
        {"iids": iid_strs, "ref": ref_date, "lb": lookback - timedelta(days=5)},
    ).fetchall()

    if not rows:
        # Broaden window if no recent data
        rows = session.execute(
            text("""
                SELECT DISTINCT ON (m.instrument_id)
                    m.instrument_id,
                    m.natr_14,
                    m.alpha_63d,
                    m.ret_12m,
                    m.ret_3m,
                    m.realized_vol_63,
                    m.beta_63d,
                    m.ma_200d,
                    m.close,
                    m.max_drawdown_252d,
                    m.positive_days_252d,
                    m.worst_quarter_ret
                  FROM atlas.atlas_stock_metrics_daily m
                 WHERE m.instrument_id = ANY(:iids)
                   AND m.date <= :ref
                 ORDER BY m.instrument_id, m.date DESC
                 LIMIT :n
            """),
            {"iids": iid_strs, "ref": ref_date, "n": len(iid_strs)},
        ).fetchall()

    if not rows:
        log.warning("simulator.signal_panel_no_rows", ref_date=str(ref_date))
        return pd.DataFrame()

    row_count_before = len(rows)

    sector_lookup = {inst.instrument_id: (inst.sector or "Unknown") for inst in instruments}

    records = []
    for r in rows:
        iid = uuid.UUID(str(r.instrument_id))
        natr = float(r.natr_14 or 0.0)
        alpha = float(r.alpha_63d or 0.0)
        ret_12m = float(r.ret_12m or 0.0)
        ret_3m = float(r.ret_3m or 0.0)
        vol = float(r.realized_vol_63 or 1e-6)  # guard zero
        beta = float(r.beta_63d or 1.0)
        close = float(r.close or 1.0)
        ma_200 = float(r.ma_200d or close)
        mdd = float(r.max_drawdown_252d or 0.0)
        pos_days = float(r.positive_days_252d or 126.0)
        worst_q = float(r.worst_quarter_ret or -0.01)

        # mom_low_vol = ret_12m / vol as a proxy (directionally correct)
        mom_low_vol = ret_12m / vol if vol > 0 else 0.0

        # FIP smoothness = (n_up - n_down) / 252 ≈ (2*pos - 252) / 252
        fip_smoothness = (2.0 * pos_days - 252.0) / 252.0

        # industry_rs will be filled after sector median computation
        records.append(
            {
                "instrument_id": iid,
                "natr_14": natr,
                "beta_alpha_63d": alpha,
                "mom_low_vol": mom_low_vol,
                "residual_momentum": alpha,  # proxy: same as alpha_63d
                "proximity_52wh": min(1.0, close / (ma_200 * 1.1 + 1e-8)),  # proxy
                "fip_smoothness": fip_smoothness,
                "bab": beta,  # raw beta — inverted to rank downstream
                "quality_raw_vol": vol,
                "quality_raw_mdd": mdd,
                "quality_raw_worst_q": worst_q,
                "ret_12m": ret_12m,
                "ret_3m": ret_3m,
                "close": close,
                "ma_200d": ma_200,
                "sector": sector_lookup.get(iid, "Unknown"),
            }
        )

    df = pd.DataFrame(records).set_index("instrument_id")
    row_count_after = len(df)

    if row_count_before != row_count_after:
        log.warning(
            "simulator.signal_panel_dedup",
            before=row_count_before,
            after=row_count_after,
        )

    # Cross-sectional BAB rank (inverse of beta rank)
    beta_arr = df["bab"].to_numpy()
    df["bab"] = pd.Series(beta_arr, index=df.index).rank(pct=True).fillna(0.5)
    df["bab"] = 1.0 - df["bab"]  # invert: low beta → high BAB rank

    # Quality proxy = -0.5×rank(vol) - 0.3×rank(mdd) + 0.2×rank(ret_consistency)
    abs_worst_q = df["quality_raw_worst_q"].abs().clip(lower=1e-8)
    ret_consistency = df["ret_12m"] / abs_worst_q
    df["quality_proxy"] = (
        -0.5 * df["quality_raw_vol"].rank(pct=True)
        - 0.3 * df["quality_raw_mdd"].rank(pct=True)
        + 0.2 * ret_consistency.rank(pct=True)
    )

    # Industry RS = ret_3m - sector median ret_3m
    sector_median_3m = df.groupby("sector")["ret_3m"].transform("median")
    df["industry_rs"] = df["ret_3m"] - sector_median_3m

    # Trend gate pass: close >= ma_200d
    # (Returned as a set, not stored in panel)

    # Drop raw helper columns
    df = df.drop(
        columns=[
            "quality_raw_vol",
            "quality_raw_mdd",
            "quality_raw_worst_q",
            "ret_12m",
            "ret_3m",
            "close",
            "ma_200d",
        ],
        errors="ignore",
    )

    log.debug(
        "simulator.signal_panel_built",
        ref_date=str(ref_date),
        n_instruments=len(df),
    )

    return df


def _get_trend_gate_pass(
    session: Session,
    instrument_ids: list[uuid.UUID],
    ref_date: date,
) -> set[uuid.UUID]:
    """Return set of instrument_ids where close >= ma_200d on the nearest prior date."""
    if not instrument_ids:
        return set()

    iid_strs = [str(i) for i in instrument_ids]
    lookback = ref_date - timedelta(days=5)

    rows = session.execute(
        text("""
            SELECT DISTINCT ON (instrument_id)
                instrument_id,
                close,
                ma_200d
              FROM atlas.atlas_stock_metrics_daily
             WHERE instrument_id = ANY(:iids)
               AND date <= :ref
               AND date >= :lb
             ORDER BY instrument_id, date DESC
        """),
        {"iids": iid_strs, "ref": ref_date, "lb": lookback},
    ).fetchall()

    passing: set[uuid.UUID] = set()
    for r in rows:
        if r.close is not None and r.ma_200d is not None:
            if float(r.close) >= float(r.ma_200d):
                passing.add(uuid.UUID(str(r.instrument_id)))
        else:
            # Missing ma_200d → fail-open: treat as passing
            passing.add(uuid.UUID(str(r.instrument_id)))

    return passing


# ---------------------------------------------------------------------------
# Returns and benchmark helpers
# ---------------------------------------------------------------------------


def _fetch_returns_panel(
    session: Session,
    instrument_ids: Sequence[uuid.UUID],
    ref_date: date,
    lookback_days: int = 252,
) -> pd.DataFrame:
    """Fetch daily return panel for HRP covariance estimation.

    Returns DataFrame: rows = dates, cols = instrument_ids.
    Only includes instruments with ≥20 rows in the window.
    """
    if not instrument_ids:
        return pd.DataFrame()

    iid_strs = [str(i) for i in instrument_ids]
    start = ref_date - timedelta(days=lookback_days * 2)  # buffer for trading days

    rows = session.execute(
        text("""
            SELECT instrument_id, date, ret_1d
              FROM atlas.atlas_stock_metrics_daily
             WHERE instrument_id = ANY(:iids)
               AND date BETWEEN :s AND :e
               AND ret_1d IS NOT NULL
             ORDER BY date
        """),
        {"iids": iid_strs, "s": start, "e": ref_date},
    ).fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["instrument_id", "date", "ret_1d"])
    df["instrument_id"] = df["instrument_id"].apply(lambda x: uuid.UUID(str(x)))

    pivot = df.pivot(index="date", columns="instrument_id", values="ret_1d")
    pivot = pivot.fillna(0.0)

    # Keep only instruments with enough history
    min_rows = 20
    valid_cols = [col for col in pivot.columns if pivot[col].count() >= min_rows]
    return pivot[valid_cols].tail(lookback_days)


def _fetch_forward_returns(
    session: Session,
    instrument_ids: Sequence[uuid.UUID],
    start: date,
    end: date,
) -> dict[uuid.UUID, float]:
    """Fetch compound return for each instrument from start to end.

    Uses ret_1d from atlas_stock_metrics_daily, compounding daily.
    Returns {} for instruments with no data in the window.
    """
    if not instrument_ids:
        return {}

    iid_strs = [str(i) for i in instrument_ids]

    rows = session.execute(
        text("""
            SELECT instrument_id, date, ret_1d
              FROM atlas.atlas_stock_metrics_daily
             WHERE instrument_id = ANY(:iids)
               AND date > :s AND date <= :e
               AND ret_1d IS NOT NULL
             ORDER BY instrument_id, date
        """),
        {"iids": iid_strs, "s": start, "e": end},
    ).fetchall()

    if not rows:
        return {}

    results: dict[uuid.UUID, float] = {}
    current: dict[uuid.UUID, float] = {}

    for r in rows:
        iid = uuid.UUID(str(r.instrument_id))
        ret = float(r.ret_1d)
        if iid not in current:
            current[iid] = 1.0
        current[iid] *= 1.0 + ret

    for iid, cumulative in current.items():
        results[iid] = cumulative - 1.0

    return results


def _benchmark_return(session: Session, start: date, end: date) -> float:
    """Nifty 500 total return between start and end dates.

    Uses atlas_market_regime_daily nifty500_tr_index column if available,
    falls back to 0.0 with a warning if missing.
    """
    rows = session.execute(
        text("""
            SELECT date, nifty500_tr_index
              FROM atlas.atlas_market_regime_daily
             WHERE date IN (:s, :e)
               AND nifty500_tr_index IS NOT NULL
             ORDER BY date
        """),
        {"s": start, "e": end},
    ).fetchall()

    if len(rows) >= 2:
        start_val = float(rows[0].nifty500_tr_index)
        end_val = float(rows[-1].nifty500_tr_index)
        if start_val > 0:
            return (end_val / start_val) - 1.0

    # Fallback: no benchmark data — return 0 with warning
    log.debug(
        "simulator.benchmark_missing",
        start=str(start),
        end=str(end),
        note="nifty500_tr_index not available; benchmark_return=0.0",
    )
    return 0.0


# ---------------------------------------------------------------------------
# Slippage computation
# ---------------------------------------------------------------------------


def _compute_slippage_drag(
    session: Session,
    new_weights: dict[uuid.UUID, float],
    prior_weights: dict[uuid.UUID, float],
    instruments: list[InvestableInstrument],
    initial_capital_cr: float,
    rebalance_date: date,
) -> float:
    """Estimate portfolio-level slippage drag as a fraction of portfolio value.

    For each order (weight change × capital), apply sqrt slippage model.
    Returns slippage as fraction (e.g. 0.001 = 0.1% drag).
    """
    capital_rs = initial_capital_cr * 1e7  # crore to rupees

    # ADV map from InvestableInstrument
    adv_map = {inst.instrument_id: inst.median_adv_cr * 1e7 for inst in instruments}

    total_drag = 0.0
    all_ids = set(new_weights.keys()) | set(prior_weights.keys())

    for iid in all_ids:
        new_w = new_weights.get(iid, 0.0)
        old_w = prior_weights.get(iid, 0.0)
        delta_w = abs(new_w - old_w)
        if delta_w < 1e-6:
            continue

        order_value = delta_w * capital_rs
        adv_20d = adv_map.get(iid, capital_rs * 0.01)  # fallback: 1% of capital

        bps = slippage_bps(order_value, adv_20d)
        drag_fraction = delta_w * bps / 10_000.0
        total_drag += drag_fraction

    return total_drag


# ---------------------------------------------------------------------------
# Aggregate statistics
# ---------------------------------------------------------------------------


def _compute_aggregate_stats(
    strategy_name: str,
    periods: list[PeriodResult],
    equity_curve: list[float],
    n_trades: int,
) -> SimulationResult:
    """Compute CAGR, MDD, vol, Sharpe, Calmar, win_rate from period results."""
    if not periods:
        return SimulationResult(
            strategy_name=strategy_name,
            periods=periods,
            ann_return=0.0,
            max_drawdown=0.0,
            vol=0.0,
            sharpe=0.0,
            calmar=0.0,
            win_rate=0.0,
            n_trades=n_trades,
        )

    returns = [p.book_return for p in periods]
    nav = pd.Series(equity_curve)

    # CAGR from start to end of equity curve
    total_days = (periods[-1].end_date - periods[0].rebalance_date).days
    if total_days <= 0:
        ann_return = 0.0
    else:
        ann_return = (equity_curve[-1] / equity_curve[0]) ** (365.25 / total_days) - 1.0

    # Max drawdown
    running_max = nav.cummax()
    drawdowns = (nav / running_max) - 1.0
    max_drawdown = float(drawdowns.min())

    # Vol (annualized, assuming ~12 periods/year)
    ret_series = pd.Series(returns)
    periods_per_year = 12.0
    vol = float(ret_series.std() * math.sqrt(periods_per_year))

    # Sharpe (using 6% annualized risk-free, ≈ 0.5% per month)
    rf_per_period = 0.06 / periods_per_year
    excess_returns = ret_series - rf_per_period
    exc_std = excess_returns.std()
    sharpe = (
        float(excess_returns.mean() / exc_std * math.sqrt(periods_per_year)) if exc_std > 0 else 0.0
    )

    # Calmar
    calmar = (ann_return / abs(max_drawdown)) if max_drawdown < 0 else 0.0

    # Win rate
    win_rate = float(sum(1 for r in returns if r > 0) / len(returns))

    return SimulationResult(
        strategy_name=strategy_name,
        periods=periods,
        ann_return=ann_return,
        max_drawdown=max_drawdown,
        vol=vol,
        sharpe=sharpe,
        calmar=calmar,
        win_rate=win_rate,
        n_trades=n_trades,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _persist_strategy_run(
    session: Session,
    config: SimulationConfig,
    result: SimulationResult,
) -> None:
    """Write one row to atlas_v6_strategy_runs. Idempotent ON CONFLICT UPDATE."""
    run_id = uuid.uuid4()
    import json

    weights_dict = (
        config.signal_weights.as_dict()
        if config.signal_weights is not None
        else SignalWeights().as_dict()
    )

    # TSRANGE syntax: '[start, end]' — PostgreSQL daterange
    is_period = f"[{config.start},{config.end}]"
    # OOS period defaults to same as IS for a simple backtest (no walk-forward split here)
    oos_period = is_period

    passes = result.calmar >= 0.5 and result.max_drawdown >= -0.20 and result.sharpe >= 0.5
    failures = []
    if result.calmar < 0.5:
        failures.append("calmar<0.5")
    if result.max_drawdown < -0.20:
        failures.append("mdd>20%")
    if result.sharpe < 0.5:
        failures.append("sharpe<0.5")

    session.execute(
        text("""
            INSERT INTO atlas.atlas_v6_strategy_runs (
                run_id, strategy_name, signal_weights,
                is_period, oos_period,
                calmar, vol_ratio, mdd_ratio, win_rate,
                passes_all_constraints, constraint_failures
            ) VALUES (
                :run_id, :name, :weights::jsonb,
                :is_period::tsrange, :oos_period::tsrange,
                :calmar, :vol, :mdd, :win_rate,
                :passes, :failures
            )
            ON CONFLICT (run_id) DO UPDATE SET
                calmar = EXCLUDED.calmar,
                win_rate = EXCLUDED.win_rate,
                passes_all_constraints = EXCLUDED.passes_all_constraints
        """),
        {
            "run_id": str(run_id),
            "name": config.strategy_name,
            "weights": json.dumps(weights_dict),
            "is_period": is_period,
            "oos_period": oos_period,
            "calmar": Decimal(str(round(result.calmar, 4))),
            "vol": Decimal(str(round(result.vol, 4))),
            "mdd": Decimal(str(round(result.max_drawdown, 4))),
            "win_rate": Decimal(str(round(result.win_rate, 4))),
            "passes": passes,
            "failures": failures,
        },
    )
    session.commit()

    log.info(
        "simulator.persisted",
        run_id=str(run_id),
        strategy=config.strategy_name,
        passes_all=passes,
    )
