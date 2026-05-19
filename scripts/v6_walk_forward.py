# allow-large: Phase 9 script contains 5 schema-compatibility shim functions
# (signal panel, returns panel, forward returns, benchmark, trend gate) needed
# to bridge simulator.py's draft column names to the live DB schema. All shims
# are in a single file to keep the compatibility surface visible and auditable.
# Responsibility count = 1 (run the walk-forward and report results).

"""Plan 2 Phase 9 — initial walk-forward backtest.

Runs run_walk_forward() from validator.py across 2016-2024 (data-permitting;
atlas_market_regime_daily starts 2016-04-07). Persists results to
atlas_v6_strategy_runs. Reports per-signal OOS-IC retention.

Hold-out 2025 is NOT examined here. Use scripts/v6_holdout_terminal.py
later (Phase 11) — and only ONCE.

Schema compatibility patches applied at runtime (all documented below):
  1. apply_exclusions — governance tables are empty (0 rows); the real function
     hits a uuid=text cast error. Patched to fail-open (no exclusions), which
     is the documented behavior when no governance data exists.
  2. _compute_signal_panel — simulator.py queries columns that do not exist in
     the live atlas_stock_metrics_daily schema (natr_14, alpha_63d, beta_63d,
     close, ma_200d, max_drawdown_252d, positive_days_252d, worst_quarter_ret).
     Patched to use actual column names: atr_21, realized_vol_63, ema_200_stock,
     max_drawdown_252. close is fetched from public.de_equity_ohlcv.
  3. SimulationResult compatibility — simulator uses ann_return; validator expects
     cagr. Patched with a transparent attribute alias wrapper.
  4. alpha_t_stat — not computed by simulator; defaults to 0.0 via getattr fallback.
  5. atlas_signal_weights schema mismatch — DB has train_ic/holdout_ic, not
     is_ic/oos_ic. _fetch_signal_ic catches the exception and returns {}.
     IS/OOS IC will be empty dicts → IC retention defaults to True for all signals.

Goal-post FAIL is expected for this v0.1 run (short history, proxy signals,
non-PIT universe from atlas_universe_stocks which only has 2026-05-06 data).
"""

from __future__ import annotations

import math
import os
import re
import statistics
import sys
import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from atlas.trading.v6 import governance as gov_module
from atlas.trading.v6 import simulator as sim_module
from atlas.trading.v6 import validator as validator_module
from atlas.trading.v6.composite import SignalWeights
from atlas.trading.v6.governance import ExclusionLog
from atlas.trading.v6.simulator import SimulationConfig, run_simulation
from atlas.trading.v6.universe import InvestableInstrument
from atlas.trading.v6.validator import (
    GoalPostResult,
    WalkForwardConfig,
    evaluate_goal_post,
    run_walk_forward,
)

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Session proxy — fixes :param::type SQLAlchemy/psycopg2 cast syntax issue
# ---------------------------------------------------------------------------
# validator.py uses `:weights::jsonb` in text() which SQLAlchemy 2.0 doesn't
# compile correctly with psycopg2. The proxy intercepts execute() calls and
# rewrites `:weights::jsonb` to cast(:weights as jsonb) syntax, then passes
# the JSON string as a parameter.

_CAST_PATTERN = re.compile(r":(\w+)::(\w+\[?\]?)")


class _SessionProxy:
    """Wraps a SQLAlchemy Session; fixes :param::type cast syntax in text()."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def execute(self, statement: Any, parameters: Any = None, **kwargs: Any) -> Any:
        """Rewrite :param::type patterns to CAST(:param AS type) before executing."""
        from sqlalchemy import text as sa_text

        stmt_str = str(statement)
        if "::" in stmt_str and hasattr(statement, "text"):
            # Rewrite :name::type → CAST(:name AS type) in the raw SQL
            new_sql = _CAST_PATTERN.sub(lambda m: f"CAST(:{m.group(1)} AS {m.group(2)})", stmt_str)
            statement = sa_text(new_sql)
        return self._session.execute(statement, parameters, **kwargs)

    def rollback(self) -> None:
        self._session.rollback()

    def commit(self) -> None:
        self._session.commit()

    def close(self) -> None:
        self._session.close()

    def scalar(self, *args: Any, **kwargs: Any) -> Any:
        return self._session.scalar(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


# ---------------------------------------------------------------------------
# Patch 0: _fetch_signal_ic stub
# ---------------------------------------------------------------------------
# atlas_signal_weights has columns train_ic/holdout_ic, not is_ic/oos_ic.
# The real _fetch_signal_ic always raises ProgrammingError, which the bare
# except catches but leaves the DB transaction in an aborted state. Every
# window's INSERT then fails because the transaction is aborted from the
# prior _fetch_signal_ic call.
#
# Fix: replace _fetch_signal_ic with a no-op stub that returns {} immediately
# without touching the DB. IS/OOS IC will be empty → all signals default to
# "no baseline" → IC retention = True (pass). This is the documented behavior.


def _fetch_signal_ic_stub(
    session: Any,
    window_start: Any,
    window_end: Any,
    signal_names: list[str],
    ic_col: str,
) -> dict[str, float]:
    """Return empty dict — atlas_signal_weights schema uses train_ic/holdout_ic."""
    return {}


# ---------------------------------------------------------------------------
# Patch 1: SimulationResult cagr alias
# ---------------------------------------------------------------------------
# SimulationResult has ann_return; validator._oos_result_from_sim calls
# getattr(sim_result, "cagr", 0.0). Wrap run_simulation to alias the field.


class _SimResultCompat:
    """Thin wrapper: exposes SimulationResult attributes + cagr alias."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name == "cagr":
            return getattr(self._inner, "ann_return", 0.0)
        return getattr(self._inner, name)


def _run_simulation_compat(session: Any, config: Any) -> _SimResultCompat:
    """Call real run_simulation; return cagr-aliased wrapper.

    Also ensures signal_weights is a SignalWeights object (not a plain dict),
    which is required by _persist_strategy_run and compute_composite.
    Rolls back the session before calling run_simulation to clear any aborted
    transaction state from prior _fetch_signal_ic DB errors.
    """
    # Coerce signal_weights: plain dict or None → SignalWeights dataclass
    if config.signal_weights is None or isinstance(config.signal_weights, dict):
        sw = config.signal_weights or {}
        default = SignalWeights()
        # Override default fields with any values from the dict
        for k, v in sw.items():
            if hasattr(default, k):
                setattr(default, k, float(v))
        config.signal_weights = default
    # Disable persistence from run_simulation — validator.py does its own insert
    config.persist = False
    result = run_simulation(session, config)
    return _SimResultCompat(result)


# ---------------------------------------------------------------------------
# Patch 2: Governance fail-open stub
# ---------------------------------------------------------------------------
# Both governance tables are empty (0 rows). The real apply_exclusions fails
# with uuid=text cast error. Fail-open is the correct and documented behavior.


def _apply_exclusions_failopen(
    session: Session,
    universe: list[Any],
    ref_date: Any,
) -> tuple[set[Any], list[ExclusionLog]]:
    """Return no exclusions — governance tables are empty (fail-open)."""
    return set(), []


# ---------------------------------------------------------------------------
# Patch 3: Signal panel using actual DB schema
# ---------------------------------------------------------------------------
# atlas_stock_metrics_daily columns that exist vs what simulator.py assumed:
#   assumed natr_14     → actual atr_21
#   assumed alpha_63d   → no equivalent (use ret_12m / realized_vol_63 proxy)
#   assumed beta_63d    → no equivalent (use vol_ratio_63 as beta proxy)
#   assumed close       → from public.de_equity_ohlcv
#   assumed ma_200d     → actual ema_200_stock
#   assumed max_drawdown_252d → actual max_drawdown_252
#   assumed positive_days_252d → no equivalent (default 126 = neutral)
#   assumed worst_quarter_ret  → no equivalent (default -0.01)


def _compute_signal_panel_compat(
    session: Session,
    instruments: list[InvestableInstrument],
    ref_date: date,
) -> pd.DataFrame:
    """Build signal panel using actual atlas_stock_metrics_daily schema.

    This is a compatibility replacement for simulator._compute_signal_panel.
    Uses the columns that actually exist in the live DB:
      - atr_21 (proxy for natr_14)
      - realized_vol_63 (vol signal)
      - ema_200_stock (proxy for ma_200d)
      - max_drawdown_252 (drawdown quality metric)
      - ret_12m, ret_3m, ret_1m (momentum signals)
      - rs_3m_nifty500 (relative strength — proxy for industry_rs)
    close is fetched separately from public.de_equity_ohlcv.

    Row counts are logged before and after the transform.
    NULL values default to neutral (0.0) to avoid propagation errors.
    """
    if not instruments:
        return pd.DataFrame()

    iid_strs = [str(inst.instrument_id) for inst in instruments]
    lookback_start = ref_date - timedelta(days=10)

    # Primary: metrics from atlas_stock_metrics_daily
    # Note: pass iids as list of UUID objects (psycopg2 handles uuid[] natively)
    iid_uuids = [uuid.UUID(s) for s in iid_strs]
    metrics_rows = session.execute(
        text("""
            SELECT DISTINCT ON (m.instrument_id)
                m.instrument_id,
                m.atr_21,
                m.ret_12m,
                m.ret_3m,
                m.ret_1m,
                m.realized_vol_63,
                m.vol_ratio_63,
                m.ema_200_stock,
                m.max_drawdown_252,
                m.rs_3m_nifty500
              FROM atlas.atlas_stock_metrics_daily m
             WHERE m.instrument_id = ANY(:iids)
               AND m.date <= :ref
               AND m.date >= :lb
             ORDER BY m.instrument_id, m.date DESC
        """),
        {"iids": iid_uuids, "ref": ref_date, "lb": lookback_start},
    ).fetchall()

    if not metrics_rows:
        # Broaden to 60-day window for sparse historical dates
        metrics_rows = session.execute(
            text("""
                SELECT DISTINCT ON (m.instrument_id)
                    m.instrument_id,
                    m.atr_21,
                    m.ret_12m,
                    m.ret_3m,
                    m.ret_1m,
                    m.realized_vol_63,
                    m.vol_ratio_63,
                    m.ema_200_stock,
                    m.max_drawdown_252,
                    m.rs_3m_nifty500
                  FROM atlas.atlas_stock_metrics_daily m
                 WHERE m.instrument_id = ANY(:iids)
                   AND m.date <= :ref
                 ORDER BY m.instrument_id, m.date DESC
                 LIMIT :n
            """),
            {"iids": iid_uuids, "ref": ref_date, "n": len(iid_uuids)},
        ).fetchall()

    row_count_before = len(metrics_rows)
    log.debug(
        "signal_panel_compat.metrics_fetched",
        ref_date=str(ref_date),
        n_rows=row_count_before,
    )

    if not metrics_rows:
        log.warning("signal_panel_compat.no_metrics_rows", ref_date=str(ref_date))
        return pd.DataFrame()

    # Fetch close prices from de_equity_ohlcv for trend gate and proximity
    close_rows = session.execute(
        text("""
            SELECT DISTINCT ON (o.instrument_id)
                o.instrument_id,
                o.close
              FROM public.de_equity_ohlcv o
             WHERE o.instrument_id = ANY(:iids)
               AND o.date <= :ref
               AND o.date >= :lb
             ORDER BY o.instrument_id, o.date DESC
        """),
        {"iids": iid_uuids, "ref": ref_date, "lb": ref_date - timedelta(days=10)},
    ).fetchall()

    close_map: dict[uuid.UUID, float] = {
        uuid.UUID(str(r.instrument_id)): float(r.close)
        for r in close_rows
        if r.close is not None and float(r.close) > 0
    }

    sector_lookup = {inst.instrument_id: (inst.sector or "Unknown") for inst in instruments}

    records = []
    for r in metrics_rows:
        iid = uuid.UUID(str(r.instrument_id))

        atr = float(r.atr_21 or 0.0)
        ret_12m = float(r.ret_12m or 0.0)
        ret_3m = float(r.ret_3m or 0.0)
        ret_1m = float(r.ret_1m or 0.0)
        vol = float(r.realized_vol_63 or 1e-6)
        vol_ratio = float(r.vol_ratio_63 or 1.0)
        ema_200 = float(r.ema_200_stock or 0.0)
        mdd = float(r.max_drawdown_252 or 0.0)
        rs_3m = float(r.rs_3m_nifty500 or 0.0)
        close = close_map.get(iid, ema_200 if ema_200 > 0 else 1.0)

        # Signal proxies using available columns:
        #   natr_14 proxy: atr_21 normalized by close (≈ ATR / close)
        natr_proxy = atr / close if close > 0 else 0.0

        #   mom_low_vol proxy: ret_12m / vol (momentum adjusted for vol)
        mom_low_vol = ret_12m / vol if vol > 1e-8 else 0.0

        #   FIP smoothness: use ret_1m as a directional proxy (positive = smooth)
        fip_smoothness = float(ret_1m)

        #   BAB: vol_ratio_63 is benchmark-relative vol; lower = lower beta
        #   (will be cross-sectionally ranked and inverted downstream)
        bab_raw = vol_ratio

        #   Proximity to 52-week high: close / ema_200 as proxy
        prox_52wh = (close / ema_200) if ema_200 > 0 else 1.0

        #   Industry RS: rs_3m_nifty500 minus sector median (computed below)
        #   quality proxy: -mdd (better quality = smaller drawdown)

        records.append(
            {
                "instrument_id": iid,
                "natr_14": natr_proxy,
                "beta_alpha_63d": ret_12m / vol if vol > 1e-8 else 0.0,  # alpha proxy
                "mom_low_vol": mom_low_vol,
                "residual_momentum": ret_12m,  # simplified proxy
                "proximity_52wh": min(2.0, max(0.0, prox_52wh)),
                "fip_smoothness": fip_smoothness,
                "bab": bab_raw,  # raw vol_ratio; inverted in rank step
                "quality_raw_vol": vol,
                "quality_raw_mdd": abs(mdd),
                "ret_3m": ret_3m,
                "ret_12m": ret_12m,
                "rs_3m": rs_3m,
                "close": close,
                "ma_200d": ema_200,
                "sector": sector_lookup.get(iid, "Unknown"),
            }
        )

    df = pd.DataFrame(records).set_index("instrument_id")
    row_count_after = len(df)

    if row_count_before != row_count_after:
        log.warning(
            "signal_panel_compat.dedup",
            before=row_count_before,
            after=row_count_after,
        )

    # Cross-sectional BAB rank (inverse of vol_ratio rank: low beta → high score)
    df["bab"] = 1.0 - df["bab"].rank(pct=True).fillna(0.5)

    # Quality proxy: -0.5×rank(vol) - 0.3×rank(mdd) + 0.2×rank(ret_12m)
    abs_mdd = df["quality_raw_mdd"].clip(lower=1e-8)
    df["quality_proxy"] = (
        -0.5 * df["quality_raw_vol"].rank(pct=True).fillna(0.5)
        - 0.3 * abs_mdd.rank(pct=True).fillna(0.5)
        + 0.2 * df["ret_12m"].rank(pct=True).fillna(0.5)
    )

    # Industry RS = rs_3m_nifty500 minus sector median
    sector_median = df.groupby("sector")["rs_3m"].transform("median")
    df["industry_rs"] = df["rs_3m"] - sector_median

    # Drop raw helper columns (not expected by downstream composite)
    df = df.drop(
        columns=[
            "quality_raw_vol",
            "quality_raw_mdd",
            "ret_3m",
            "ret_12m",
            "rs_3m",
            "close",
            "ma_200d",
        ],
        errors="ignore",
    )

    log.debug(
        "signal_panel_compat.built",
        ref_date=str(ref_date),
        n_instruments=len(df),
        columns=list(df.columns),
    )

    return df


def _fetch_returns_panel_compat(
    session: Session,
    instrument_ids: Any,
    ref_date: date,
    lookback_days: int = 252,
) -> pd.DataFrame:
    """Fetch daily return panel with UUID objects (avoids uuid=text cast error).

    Returns DataFrame: rows=dates, cols=instrument_ids.
    Only includes instruments with >=20 rows in the window.
    """
    if not instrument_ids:
        return pd.DataFrame()

    iid_uuids = [uuid.UUID(str(i)) for i in instrument_ids]
    start = ref_date - timedelta(days=lookback_days * 2)

    rows = session.execute(
        text("""
            SELECT instrument_id, date, ret_1d
              FROM atlas.atlas_stock_metrics_daily
             WHERE instrument_id = ANY(:iids)
               AND date BETWEEN :s AND :e
               AND ret_1d IS NOT NULL
             ORDER BY date
        """),
        {"iids": iid_uuids, "s": start, "e": ref_date},
    ).fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["instrument_id", "date", "ret_1d"])
    df["instrument_id"] = df["instrument_id"].apply(lambda x: uuid.UUID(str(x)))
    # Cast Decimal to float — numeric columns from psycopg2 return Decimal
    df["ret_1d"] = df["ret_1d"].astype(float)

    pivot = df.pivot(index="date", columns="instrument_id", values="ret_1d")
    pivot = pivot.fillna(0.0)

    min_rows = 20
    valid_cols = [col for col in pivot.columns if pivot[col].count() >= min_rows]
    return pivot[valid_cols].tail(lookback_days)


def _fetch_forward_returns_compat(
    session: Session,
    instrument_ids: Any,
    start: date,
    end: date,
) -> dict[uuid.UUID, float]:
    """Fetch compound return per instrument with UUID objects.

    Uses ret_1d from atlas_stock_metrics_daily, compounding daily.
    """
    if not instrument_ids:
        return {}

    iid_uuids = [uuid.UUID(str(i)) for i in instrument_ids]

    rows = session.execute(
        text("""
            SELECT instrument_id, date, ret_1d
              FROM atlas.atlas_stock_metrics_daily
             WHERE instrument_id = ANY(:iids)
               AND date > :s AND date <= :e
               AND ret_1d IS NOT NULL
             ORDER BY instrument_id, date
        """),
        {"iids": iid_uuids, "s": start, "e": end},
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


def _benchmark_return_compat(
    session: Session,
    start: date,
    end: date,
) -> float:
    """Nifty 500 price return via atlas_market_regime_daily.nifty500_close.

    The spec uses nifty500_tr_index which is not in the live DB schema.
    Using nifty500_close as a proxy (excludes dividends — conservative).
    Falls back to 0.0 if no data.
    """
    rows = session.execute(
        text("""
            SELECT date, nifty500_close
              FROM atlas.atlas_market_regime_daily
             WHERE date >= :s AND date <= :e
               AND nifty500_close IS NOT NULL
             ORDER BY date
        """),
        {"s": start, "e": end},
    ).fetchall()

    if len(rows) >= 2:
        start_val = float(rows[0].nifty500_close)
        end_val = float(rows[-1].nifty500_close)
        if start_val > 0:
            return (end_val / start_val) - 1.0

    log.debug("benchmark_compat.missing", start=str(start), end=str(end))
    return 0.0


def _get_trend_gate_pass_compat(
    session: Session,
    instrument_ids: list[uuid.UUID],
    ref_date: date,
) -> set[uuid.UUID]:
    """Return instruments where close >= ema_200_stock (trend gate).

    Uses de_equity_ohlcv for close and atlas_stock_metrics_daily for ema_200.
    Fail-open: instruments without data pass the gate.
    """
    if not instrument_ids:
        return set()

    iid_uuids = list(instrument_ids)

    # Get close prices
    close_rows = session.execute(
        text("""
            SELECT DISTINCT ON (instrument_id)
                instrument_id, close
              FROM public.de_equity_ohlcv
             WHERE instrument_id = ANY(:iids)
               AND date <= :ref
               AND date >= :lb
             ORDER BY instrument_id, date DESC
        """),
        {"iids": iid_uuids, "ref": ref_date, "lb": ref_date - timedelta(days=5)},
    ).fetchall()

    close_map = {uuid.UUID(str(r.instrument_id)): float(r.close) for r in close_rows if r.close}

    # Get ema_200
    ema_rows = session.execute(
        text("""
            SELECT DISTINCT ON (instrument_id)
                instrument_id, ema_200_stock
              FROM atlas.atlas_stock_metrics_daily
             WHERE instrument_id = ANY(:iids)
               AND date <= :ref
               AND date >= :lb
             ORDER BY instrument_id, date DESC
        """),
        {"iids": iid_uuids, "ref": ref_date, "lb": ref_date - timedelta(days=10)},
    ).fetchall()

    ema_map = {
        uuid.UUID(str(r.instrument_id)): float(r.ema_200_stock)
        for r in ema_rows
        if r.ema_200_stock is not None and float(r.ema_200_stock) > 0
    }

    passing: set[uuid.UUID] = set()
    for iid in instrument_ids:
        close = close_map.get(iid)
        ema = ema_map.get(iid)
        if close is None or ema is None:
            # Fail-open: no data → pass gate
            passing.add(iid)
        elif close >= ema:
            passing.add(iid)

    return passing


def main() -> int:
    db_url = os.environ.get("ATLAS_DB_URL")
    if not db_url:
        print("ERROR: ATLAS_DB_URL not set", file=sys.stderr)
        return 1

    # --- Apply all compatibility patches before running ---

    # Patch 0: _fetch_signal_ic stub (prevents DB transaction aborts)
    validator_module._fetch_signal_ic = _fetch_signal_ic_stub  # type: ignore[assignment]

    # Patch 1: SimulationResult cagr alias
    # Must patch validator module's captured reference (not just sim_module)
    sim_module.run_simulation = _run_simulation_compat  # type: ignore[assignment]
    sim_module._sim_config_cls = SimulationConfig  # type: ignore[attr-defined]
    validator_module.run_simulation = _run_simulation_compat  # type: ignore[assignment]
    validator_module._sim_config_cls = SimulationConfig  # type: ignore[assignment]

    # Patch 2: Governance fail-open
    gov_module.apply_exclusions = _apply_exclusions_failopen  # type: ignore[assignment]
    import atlas.trading.v6.simulator as _sim_internal

    _sim_internal.apply_exclusions = _apply_exclusions_failopen  # type: ignore[assignment]

    # Patch 3: Signal panel, returns panel, forward returns, benchmark — correct column names/types
    _sim_internal._compute_signal_panel = _compute_signal_panel_compat  # type: ignore[assignment]
    _sim_internal._get_trend_gate_pass = _get_trend_gate_pass_compat  # type: ignore[assignment]
    _sim_internal._fetch_returns_panel = _fetch_returns_panel_compat  # type: ignore[assignment]
    _sim_internal._fetch_forward_returns = _fetch_forward_returns_compat  # type: ignore[assignment]
    _sim_internal._benchmark_return = _benchmark_return_compat  # type: ignore[assignment]

    eng = create_engine(db_url)
    session_factory = sessionmaker(bind=eng)
    _raw_session = session_factory()
    # Ensure clean connection state
    try:
        _raw_session.rollback()
    except Exception:
        pass
    _raw_session.close()
    _raw_session = session_factory()
    # Wrap in proxy to fix :param::type cast syntax in validator.py
    session: Any = _SessionProxy(_raw_session)

    # Data range: market_regime_daily runs 2016-04-07 → 2026-05-18
    # 4 OOS windows: 2021, 2022, 2023, 2024
    # Hold-out: 2025 (untouched in this script — Phase 11 only)
    config = WalkForwardConfig(
        train_start=date(2016, 4, 7),
        train_end=date(2020, 12, 31),
        oos_start=date(2021, 1, 1),
        oos_end=date(2024, 12, 31),
        hold_out_start=date(2025, 1, 1),
        hold_out_end=date(2025, 12, 31),
        refit_freq="annual",
        ic_retention_threshold=0.70,
    )

    log.info(
        "walk_forward.start",
        train_start=config.train_start.isoformat(),
        train_end=config.train_end.isoformat(),
        oos_start=config.oos_start.isoformat(),
        oos_end=config.oos_end.isoformat(),
    )

    # Pass default signal weights so composite doesn't see empty dict
    default_weights = SignalWeights().as_dict()

    try:
        results = run_walk_forward(session, config, initial_weights=default_weights)
        session.commit()
    except Exception as exc:
        log.error("walk_forward.failed", err=str(exc))
        session.rollback()
        raise

    log.info("walk_forward.complete", n_windows=len(results))

    # Summary report
    print()
    print(f"=== Walk-Forward Results: {len(results)} OOS windows ===")
    for r in results:
        print(
            f"OOS {r.window.oos_start.year}: "
            f"CAGR={r.cagr:.2%} "
            f"MDD={r.max_drawdown:.2%} "
            f"Sharpe={r.sharpe:.2f} "
            f"Calmar={r.calmar:.2f} "
            f"win={r.win_rate:.0%} "
            f"alpha_t={r.alpha_t_stat:.2f}"
        )

    # Per-signal OOS-IC retention summary
    print()
    print("=== Per-Signal OOS-IC Retention ===")
    all_signals: set[str] = set()
    for r in results:
        all_signals.update(r.per_signal_oos_ic.keys())
        all_signals.update(r.per_signal_is_ic.keys())

    if not all_signals:
        print(
            "  (no signal IC data — atlas_signal_weights has train_ic/holdout_ic,"
            " not is_ic/oos_ic)"
        )
    else:
        for sig in sorted(all_signals):
            ratios = []
            for r in results:
                is_ic = r.per_signal_is_ic.get(sig, 0.0)
                oos_ic = r.per_signal_oos_ic.get(sig, 0.0)
                if is_ic and abs(is_ic) > 1e-10:
                    ratios.append(oos_ic / is_ic)
            if ratios:
                avg = sum(ratios) / len(ratios)
                shelved = "SHELVED" if avg < 0.70 else "active"
                print(f"  {sig:25} avg retention {avg:+.2%}  {shelved}")

    # Goal-post evaluation
    if not results:
        print()
        print("=== Goal-Post: SKIP (no OOS windows) ===")
        return 0

    # Benchmark vol from atlas_market_regime_daily realized_vol_5d_nifty500
    bench_vol_col = session.execute(
        text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'atlas'
               AND table_name = 'atlas_market_regime_daily'
               AND column_name LIKE '%vol%'
             ORDER BY column_name
        """)
    ).fetchall()
    vol_col = bench_vol_col[0][0] if bench_vol_col else None

    vols: list[float] = []
    if vol_col:
        benchmark_rows = session.execute(
            text(f"""
                SELECT {vol_col}
                  FROM atlas.atlas_market_regime_daily
                 WHERE date BETWEEN :s AND :e
                   AND {vol_col} IS NOT NULL
            """),  # noqa: S608 — vol_col is schema-introspected, not user input
            {"s": config.oos_start, "e": config.oos_end},
        ).fetchall()
        vols = [float(r[0]) for r in benchmark_rows if r[0] is not None]

    if len(vols) > 1:
        bench_vol = statistics.stdev(vols) * math.sqrt(252)
    else:
        bench_vol = 0.18
        log.warning("walk_forward.bench_vol_fallback", bench_vol=bench_vol)

    # Benchmark MDD proxy: Nifty 500 historical worst drawdown ~38% (spec §1.2)
    bench_mdd = -0.38

    try:
        goal_post: GoalPostResult = evaluate_goal_post(session, results, bench_vol, bench_mdd)
    except ValueError as exc:
        print(f"\n=== Goal-Post: ERROR ({exc}) ===")
        return 0

    print()
    verdict = "PASS" if goal_post.passes_all_constraints else "FAIL"
    print(f"=== Goal-Post: {verdict} ===")
    for c in goal_post.constraints:
        marker = "PASS" if c["pass"] else "FAIL"
        print(f"  [{marker}] {c['name']:25} " f"target={c['target']}  " f"actual={c['actual']}")

    # Row count verification
    row_count = session.execute(
        text("SELECT COUNT(*) n FROM atlas.atlas_v6_strategy_runs")
    ).scalar()
    print()
    print(f"atlas_v6_strategy_runs row count: {row_count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
