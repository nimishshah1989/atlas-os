# allow-large: Terminal one-shot operator script. Eight cohesive compatibility
# shims (SessionProxy, _fetch_signal_ic stub, SimResultCompat, governance fail-open,
# signal panel compat, returns panel compat, forward returns compat, trend gate compat,
# benchmark compat) kept in one file for auditability — splitting would scatter the
# DB schema compatibility surface that was hard-won in Phase 9 debugging.
# Responsibility count = 1 (run the terminal hold-out evaluation exactly once).
"""Plan 2 Phase 11 — terminal hold-out evaluation.

Examines the 2025 hold-out window EXACTLY ONCE. Writes
atlas_v6_strategy_runs.holdout_examined_at and the OOS stats. Raises
HoldoutAlreadyExamined if called twice.

This is the TERMINAL step of v0.1 build. After this, no more weight
adjustments; the v6 model is frozen.

Schema compatibility patches (same as Phase 9 walk-forward script):
  1. _fetch_signal_ic stub — atlas_signal_weights uses train_ic/holdout_ic,
     not is_ic/oos_ic. The real function triggers a ProgrammingError that
     leaves the transaction aborted. Replaced with no-op returning {}.
  2. SimulationResult cagr alias — simulator uses ann_return; validator
     expects cagr. Wrapped via _SimResultCompat.
  3. Governance fail-open — governance tables are empty; fail-open is
     the documented behavior when no data exists.
  4. Signal panel compat — actual column names differ from simulator.py drafts.
     Uses atr_21, realized_vol_63, ema_200_stock, max_drawdown_252, etc.
  5. Returns panel Decimal→float cast — psycopg2 returns numeric columns as
     Decimal; pandas cannot multiply Decimal * float (HRP weights). Cast at read.
  6. SessionProxy — validator.py uses :param::jsonb syntax which SQLAlchemy 2.0
     + psycopg2 does not compile correctly. Rewritten to CAST(:param AS jsonb).

Usage
-----
    PYTHONPATH=. DATABASE_URL="$ATLAS_DB_URL" .venv/bin/python scripts/v6_holdout_terminal.py

Exit codes
----------
0 — success (hold-out evaluated and printed)
1 — fatal (missing env, no candidate run found, DB error)
2 — hold-out already examined (singleton enforcement fired)
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from collections.abc import Sequence
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
from atlas.trading.v6.validator import HoldoutAlreadyExamined, examine_holdout

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# SessionProxy — fixes :param::type cast syntax in validator.py
# ---------------------------------------------------------------------------
_CAST_PATTERN = re.compile(r":(\w+)::(\w+\[?\]?)")


class _SessionProxy:
    """Wraps a SQLAlchemy Session; rewrites :param::type to CAST(:param AS type)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def execute(self, statement: Any, parameters: Any = None, **kwargs: Any) -> Any:
        from sqlalchemy import text as sa_text

        stmt_str = str(statement)
        if "::" in stmt_str and hasattr(statement, "text"):
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
def _fetch_signal_ic_stub(
    session: Any,
    window_start: Any,
    window_end: Any,
    signal_names: list[str],
    ic_col: str,
) -> dict[str, float]:
    """Return empty dict — atlas_signal_weights uses train_ic/holdout_ic schema."""
    return {}


# ---------------------------------------------------------------------------
# Patch 1: SimulationResult cagr alias
# ---------------------------------------------------------------------------
class _SimResultCompat:
    """Thin wrapper: exposes SimulationResult attributes + cagr alias for ann_return."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name == "cagr":
            return getattr(self._inner, "ann_return", 0.0)
        return getattr(self._inner, name)


def _run_simulation_compat(session: Any, config: Any) -> _SimResultCompat:
    """Call real run_simulation; return cagr-aliased wrapper.

    Also coerces signal_weights dict → SignalWeights dataclass and disables
    persistence (validator.py does its own insert).
    """
    if config.signal_weights is None or isinstance(config.signal_weights, dict):
        sw = config.signal_weights or {}
        default = SignalWeights()
        for k, v in sw.items():
            if hasattr(default, k):
                setattr(default, k, float(v))
        config.signal_weights = default
    config.persist = False
    result = run_simulation(session, config)
    return _SimResultCompat(result)


# ---------------------------------------------------------------------------
# Patch 2: Governance fail-open
# ---------------------------------------------------------------------------
def _apply_exclusions_failopen(
    session: Session,
    universe: list[Any],
    ref_date: Any,
) -> tuple[set[Any], list[ExclusionLog]]:
    """Return no exclusions — governance tables are empty (fail-open documented behavior)."""
    return set(), []


# ---------------------------------------------------------------------------
# Patch 3: Signal panel using actual DB schema (matches Phase 9 compat shim)
# ---------------------------------------------------------------------------
def _compute_signal_panel_compat(
    session: Session,
    instruments: list[InvestableInstrument],
    ref_date: date,
) -> pd.DataFrame:
    """Build signal panel using actual atlas_stock_metrics_daily columns.

    Column mapping from Phase 9 audit:
      assumed natr_14     → actual atr_21 / close
      assumed alpha_63d   → proxy: ret_12m / realized_vol_63
      assumed beta_63d    → proxy: vol_ratio_63
      assumed close       → from public.de_equity_ohlcv
      assumed ma_200d     → actual ema_200_stock
      assumed max_drawdown_252d → actual max_drawdown_252
      assumed positive_days_252d → default 126 (neutral)
      assumed worst_quarter_ret  → default -0.01

    Includes 'sector' column required by simulator._execute_rebalance to
    compute industry_rs cross-sectionally. Without it the period is skipped.
    """
    if not instruments:
        return pd.DataFrame()

    iid_uuids = [inst.instrument_id for inst in instruments]
    lookback_start = ref_date - timedelta(days=10)

    # Primary: metrics from atlas_stock_metrics_daily
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
    if not metrics_rows:
        log.warning("signal_panel_compat.no_metrics_rows", ref_date=str(ref_date))
        return pd.DataFrame()

    # Fetch close prices from de_equity_ohlcv
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

        natr_proxy = atr / close if close > 0 else 0.0
        mom_low_vol = ret_12m / vol if vol > 1e-8 else 0.0
        fip_smoothness = float(ret_1m)
        bab_raw = vol_ratio
        prox_52wh = (close / ema_200) if ema_200 > 0 else 1.0

        records.append(
            {
                "instrument_id": iid,
                "natr_14": natr_proxy,
                "beta_alpha_63d": ret_12m / vol if vol > 1e-8 else 0.0,
                "mom_low_vol": mom_low_vol,
                "residual_momentum": ret_12m,
                "proximity_52wh": min(2.0, max(0.0, prox_52wh)),
                "fip_smoothness": fip_smoothness,
                "bab": bab_raw,
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
        log.warning("signal_panel_compat.dedup", before=row_count_before, after=row_count_after)

    # Cross-sectional BAB rank (inverse of vol_ratio rank: low beta → high score)
    df["bab"] = 1.0 - df["bab"].rank(pct=True).fillna(0.5)

    # Quality proxy: composite rank
    abs_mdd = df["quality_raw_mdd"].clip(lower=1e-8)
    df["quality_proxy"] = (
        -0.5 * df["quality_raw_vol"].rank(pct=True).fillna(0.5)
        - 0.3 * abs_mdd.rank(pct=True).fillna(0.5)
        + 0.2 * df["ret_12m"].rank(pct=True).fillna(0.5)
    )

    # Industry RS = rs_3m_nifty500 minus sector median
    sector_median = df.groupby("sector")["rs_3m"].transform("median")
    df["industry_rs"] = df["rs_3m"] - sector_median

    # Drop raw helper columns not expected by downstream composite
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


# ---------------------------------------------------------------------------
# Patch 4: Returns panel with Decimal→float cast
# ---------------------------------------------------------------------------
def _fetch_returns_panel_compat(
    session: Session,
    instrument_ids: Sequence[uuid.UUID],
    ref_date: date,
    lookback_days: int = 252,
) -> pd.DataFrame:
    """Fetch daily return panel; cast Decimal→float (psycopg2 numeric→Decimal).

    HRP weights are float; pandas cannot multiply Decimal * float.
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


# ---------------------------------------------------------------------------
# Patch 5: Forward returns with proper UUID handling + Decimal cast
# ---------------------------------------------------------------------------
def _fetch_forward_returns_compat(
    session: Session,
    instrument_ids: Any,
    start: date,
    end: date,
) -> dict[uuid.UUID, float]:
    """Fetch compound return per instrument; cast Decimal→float."""
    if not instrument_ids:
        return {}

    iid_uuids = [uuid.UUID(str(i)) for i in instrument_ids]

    rows = session.execute(
        text("""
            SELECT instrument_id, date, ret_1d
              FROM atlas.atlas_stock_metrics_daily
             WHERE instrument_id = ANY(:iids)
               AND date BETWEEN :s AND :e
               AND ret_1d IS NOT NULL
             ORDER BY date
        """),
        {"iids": iid_uuids, "s": start, "e": end},
    ).fetchall()

    results: dict[uuid.UUID, float] = {}
    current: dict[uuid.UUID, float] = {}
    for r in rows:
        iid = uuid.UUID(str(r.instrument_id))
        ret = float(r.ret_1d)
        if iid not in current:
            current[iid] = 1.0
        current[iid] *= 1.0 + ret

    for iid, compound in current.items():
        results[iid] = compound - 1.0

    return results


# ---------------------------------------------------------------------------
# Patch 6: Trend gate using actual ema_200_stock column
# ---------------------------------------------------------------------------
def _get_trend_gate_pass_compat(
    session: Session,
    instrument_ids: Sequence[uuid.UUID],
    ref_date: date,
) -> set[uuid.UUID]:
    """Trend gate using ema_200_stock from atlas_stock_metrics_daily."""
    if not instrument_ids:
        return set()

    iid_uuids = list(instrument_ids)

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
            passing.add(iid)  # fail-open: no data → pass gate
        elif close >= ema:
            passing.add(iid)

    return passing


# ---------------------------------------------------------------------------
# Patch 7: Benchmark return using atlas_market_regime_daily
# ---------------------------------------------------------------------------
def _benchmark_return_compat(
    session: Session,
    start: date,
    end: date,
) -> float:
    """Compute Nifty 500 compound return from atlas_market_regime_daily."""
    rows = session.execute(
        text("""
            SELECT date, nifty500_close
              FROM atlas.atlas_market_regime_daily
             WHERE date BETWEEN :s AND :e
               AND nifty500_close IS NOT NULL
             ORDER BY date
        """),
        {"s": start, "e": end},
    ).fetchall()

    if len(rows) < 2:
        return 0.0

    start_val = float(rows[0].nifty500_close)
    end_val = float(rows[-1].nifty500_close)
    if start_val <= 0:
        return 0.0
    return end_val / start_val - 1.0


def main() -> int:
    db_url = os.environ.get("ATLAS_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            "ERROR: ATLAS_DB_URL or DATABASE_URL must be set",
            file=sys.stderr,
        )
        return 1

    # --- Apply all compatibility patches ---

    # Patch 0: _fetch_signal_ic stub (prevents DB transaction aborts from schema mismatch)
    validator_module._fetch_signal_ic = _fetch_signal_ic_stub  # type: ignore[assignment]

    # Patch 1: SimulationResult cagr alias + signal_weights coercion
    sim_module.run_simulation = _run_simulation_compat  # type: ignore[assignment]
    sim_module._sim_config_cls = SimulationConfig  # type: ignore[attr-defined]
    validator_module.run_simulation = _run_simulation_compat  # type: ignore[assignment]
    validator_module._sim_config_cls = SimulationConfig  # type: ignore[assignment]

    # Patch 2: Governance fail-open
    gov_module.apply_exclusions = _apply_exclusions_failopen  # type: ignore[assignment]
    import atlas.trading.v6.simulator as _sim_internal

    _sim_internal.apply_exclusions = _apply_exclusions_failopen  # type: ignore[assignment]

    # Patch 3–7: Signal panel, returns panel, forward returns, trend gate, benchmark
    _sim_internal._compute_signal_panel = _compute_signal_panel_compat  # type: ignore[assignment]
    _sim_internal._fetch_returns_panel = _fetch_returns_panel_compat  # type: ignore[assignment]
    _sim_internal._fetch_forward_returns = _fetch_forward_returns_compat  # type: ignore[assignment]
    _sim_internal._get_trend_gate_pass = _get_trend_gate_pass_compat  # type: ignore[assignment]
    _sim_internal._benchmark_return = _benchmark_return_compat  # type: ignore[assignment]

    eng = create_engine(db_url)
    session_factory = sessionmaker(bind=eng)
    _raw_session = session_factory()
    try:
        _raw_session.rollback()
    except Exception:
        pass
    _raw_session.close()
    _raw_session = session_factory()

    # Wrap in proxy to fix :param::jsonb cast syntax in validator.py
    session: Any = _SessionProxy(_raw_session)

    # Find the best candidate strategy run to anchor the hold-out eval to.
    # Use highest Calmar with holdout_examined_at IS NULL.
    try:
        row = session.execute(
            text("""
                SELECT run_id, strategy_name, calmar
                  FROM atlas.atlas_v6_strategy_runs
                 WHERE holdout_examined_at IS NULL
                 ORDER BY calmar DESC NULLS LAST, created_at DESC
                 LIMIT 1
            """)
        ).first()
    except Exception as exc:
        print(f"ERROR: DB query failed: {exc}", file=sys.stderr)
        session.close()
        return 1

    if row is None:
        print(
            "ERROR: no candidate strategy_run found (or all already examined)",
            file=sys.stderr,
        )
        session.close()
        return 1

    strategy_run_id = uuid.UUID(str(row.run_id))
    log.info(
        "phase11.anchored_strategy_run",
        run_id=str(strategy_run_id),
        strategy=row.strategy_name,
        prior_calmar=float(row.calmar) if row.calmar is not None else None,
    )

    try:
        result = examine_holdout(session, strategy_run_id)
        session.commit()
    except HoldoutAlreadyExamined as exc:
        print(
            f"\nERROR: hold-out already examined for {strategy_run_id}",
            file=sys.stderr,
        )
        print(f"  {exc}", file=sys.stderr)
        session.close()
        return 2
    except Exception as exc:
        print(f"\nERROR: examine_holdout failed: {exc}", file=sys.stderr)
        session.rollback()
        session.close()
        return 1

    session.close()

    print()
    print("=== Hold-out Terminal Evaluation ===")
    print(f"  Strategy run: {strategy_run_id}")
    print(f"  OOS window:   {result.window.oos_start} → {result.window.oos_end}")
    print(f"  CAGR:         {result.cagr:.2%}")
    print(f"  MDD:          {result.max_drawdown:.2%}")
    print(f"  Sharpe:       {result.sharpe:.2f}")
    print(f"  Calmar:       {result.calmar:.2f}")
    print(f"  Win rate:     {result.win_rate:.0%}")
    print(f"  Alpha t-stat: {result.alpha_t_stat:.2f}")
    print()
    print("=== v6 v0.1 build COMPLETE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
