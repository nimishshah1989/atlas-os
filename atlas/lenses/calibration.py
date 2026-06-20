"""IC calibration for the six-lens scoring engine.

Wires lens scores (atlas_lens_scores_daily) into the IC engine and persists
results to atlas_signal_ic. Walk-forward optimisation proposes IC-proportional
weights to atlas_weight_proposals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.intelligence.validation.ic_engine import (
    ICResult, compute_ic_over_window, compute_quantile_spread, compute_turnover,
)
from atlas.intelligence.validation.persistence import persist_ic_result

log = structlog.get_logger()

_LENSES = ("technical", "fundamental", "valuation", "catalyst", "flow", "policy", "composite")
_FWD_MAP: dict[int, str] = {21: "ret_1m", 63: "ret_3m", 126: "ret_6m"}
_TIERS = ("tier_1_megacap", "tier_2_largecap", "tier_3_uppermid",
          "tier_4_lowermid", "tier_5_smallcap")


@dataclass(frozen=True)
class LensICRow:
    """One lens x forward-period IC result."""
    lens: str; forward_days: int; ic: ICResult; quantile_spread: float; turnover: float


@dataclass(frozen=True)
class WeightProposal:
    """Proposed weight for one lens from walk-forward IC."""
    lens: str; weight: float; train_ic: float; test_ic: float


# -- data loaders -----------------------------------------------------------

def _load_lens_scores(engine: Engine) -> pd.DataFrame:
    cols = ", ".join(_LENSES)
    sql = f"SELECT instrument_id, date, {cols} FROM atlas.atlas_lens_scores_daily ORDER BY date"  # noqa: S608
    with open_compute_session(engine) as conn:
        df = pd.read_sql(text(sql), conn)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    for c in _LENSES:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _load_fwd_returns(engine: Engine, col: str) -> pd.DataFrame:
    sql = f"SELECT instrument_id, date, {col} AS fwd_return FROM foundation_staging.technical_daily WHERE {col} IS NOT NULL"  # noqa: S608, E501
    with open_compute_session(engine) as conn:
        df = pd.read_sql(text(sql), conn)
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"])
    return df.pivot(index="date", columns="instrument_id", values="fwd_return")


def _factor_frame(scores: pd.DataFrame, lens: str) -> pd.DataFrame:
    sub = scores[["date", "instrument_id", lens]].dropna(subset=[lens]).copy()
    return sub.rename(columns={lens: "factor"}).set_index(["date", "instrument_id"])


def _ann_spread(q_spread: float, fwd_days: int) -> float:
    return q_spread * (252 / fwd_days) if not np.isnan(q_spread) else float("nan")


# -- core calibration -------------------------------------------------------

def _compute_lens_ic(
    factor: pd.DataFrame, returns_wide: pd.DataFrame,
) -> tuple[ICResult, float, float]:
    ic = compute_ic_over_window(factor, returns_wide)
    qs = compute_quantile_spread(factor, returns_wide, n_quantiles=5)
    to = compute_turnover(factor, n_quantiles=5)
    return ic, qs, to


def calibrate_lens_ic(
    engine: Engine,
    as_of_date: date | None = None,
    forward_periods: list[int] | None = None,
) -> list[LensICRow]:
    """Compute IC for each lens vs each forward-return horizon; persist to atlas_signal_ic."""
    as_of = as_of_date or date.today()
    periods = forward_periods or [21, 63, 126]
    log.info("lens_ic_calibration_start", as_of=str(as_of), periods=periods)

    scores = _load_lens_scores(engine)
    if scores.empty:
        log.warning("lens_ic_no_scores"); return []  # noqa: E702

    results: list[LensICRow] = []
    for fwd_days in periods:
        ret_col = _FWD_MAP.get(fwd_days)
        if not ret_col:
            continue
        rw = _load_fwd_returns(engine, ret_col)
        if rw.empty:
            continue

        for lens in _LENSES:
            fac = _factor_frame(scores, lens)
            if fac.empty:
                continue
            ic, qs, to = _compute_lens_ic(fac, rw)
            results.append(LensICRow(lens, fwd_days, ic, qs, to))
            persist_ic_result(
                engine, signal_name=f"lens_{lens}", timeframe="daily",
                forward_period_days=fwd_days, rolling_window="full",
                as_of=as_of, result=ic,
                quantile_spread_ann=_ann_spread(qs, fwd_days),
                turnover_monthly=to,
            )
            log.info("lens_ic_computed", lens=lens, fwd_days=fwd_days,
                     mean_ic=round(ic.mean_ic, 4) if not np.isnan(ic.mean_ic) else None,
                     n_obs=ic.n_observations)

    log.info("lens_ic_calibration_done", n_results=len(results))
    return results


# -- walk-forward weights ---------------------------------------------------

def _compute_walk_forward_weights(
    ic_by_lens: dict[str, float],
    ir_by_lens: dict[str, float],
    min_ic: float = 0.03,
) -> dict[str, float]:
    """Weights proportional to |IC| * |IR|, normalised to 1.0."""
    raw: dict[str, float] = {}
    for lens, ic in ic_by_lens.items():
        ir = ir_by_lens.get(lens, 0.0)
        if np.isnan(ic) or np.isnan(ir) or abs(ic) < min_ic:
            continue
        raw[lens] = abs(ic) * max(abs(ir), 0.0)
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()} if total > 0 else {}


def propose_weights(
    engine: Engine,
    as_of_date: date | None = None,
    forward_days: int = 63,
    train_frac: float = 0.7,
    min_ic: float = 0.03,
) -> list[WeightProposal]:
    """Walk-forward: train/test split, IC on train, validate on test,
    propose IC*IR-proportional weights. Persists to atlas_weight_proposals."""
    as_of = as_of_date or date.today()
    scores = _load_lens_scores(engine)
    if scores.empty:
        log.warning("propose_weights_no_scores"); return []  # noqa: E702

    ret_col = _FWD_MAP.get(forward_days, "ret_3m")
    rw = _load_fwd_returns(engine, ret_col)
    if rw.empty:
        log.warning("propose_weights_no_returns"); return []  # noqa: E702

    all_dates = sorted(scores["date"].unique())
    split_idx = int(len(all_dates) * train_frac)
    if split_idx < 2 or len(all_dates) - split_idx < 2:
        log.warning("propose_weights_insufficient_dates", n=len(all_dates)); return []  # noqa: E702

    train_dates, test_dates = set(all_dates[:split_idx]), set(all_dates[split_idx:])
    train_ic: dict[str, float] = {}
    test_ic: dict[str, float] = {}
    train_ir: dict[str, float] = {}

    for lens in _LENSES:
        if lens == "composite":
            continue
        fac = _factor_frame(scores, lens)
        if fac.empty:
            continue
        tr_f = fac[fac.index.get_level_values("date").isin(train_dates)]
        tr_r = rw[rw.index.isin(train_dates)]
        tr = compute_ic_over_window(tr_f, tr_r)
        train_ic[lens] = tr.mean_ic
        train_ir[lens] = tr.mean_ic / tr.ic_std if tr.ic_std and tr.ic_std > 0 else 0.0

        te_f = fac[fac.index.get_level_values("date").isin(test_dates)]
        te_r = rw[rw.index.isin(test_dates)]
        te = compute_ic_over_window(te_f, te_r)
        test_ic[lens] = te.mean_ic

    weights = _compute_walk_forward_weights(train_ic, train_ir, min_ic=min_ic)
    if not weights:
        log.warning("propose_weights_no_qualifying_lens"); return []  # noqa: E702

    proposals = [
        WeightProposal(lens=l, weight=round(w, 6),
                       train_ic=round(train_ic.get(l, float("nan")), 6),
                       test_ic=round(test_ic.get(l, float("nan")), 6))
        for l, w in weights.items()
    ]
    for p in proposals:
        log.info("lens_weight_proposed", lens=p.lens, weight=p.weight,
                 train_ic=p.train_ic, test_ic=p.test_ic)

    _persist_proposals(engine, proposals, as_of, forward_days)
    return proposals


def _persist_proposals(
    engine: Engine, proposals: list[WeightProposal],
    as_of: date, forward_days: int,
) -> None:
    """Write proposals to atlas_weight_proposals (one row per tier)."""
    from atlas.intelligence.conviction.optimization.persistence import insert_proposal

    pw = {f"lens_{p.lens}": p.weight for p in proposals}
    cw = {f"lens_{ln}": 0.0 for ln in _LENSES if ln != "composite"}
    avg_holdout = float(np.nanmean([p.test_ic for p in proposals])) if proposals else None

    for tier in _TIERS:
        try:
            insert_proposal(engine, {
                "tier": tier, "regime": "all",
                "proposed_weights": {k: round(v, 6) for k, v in pw.items()},
                "current_weights": cw,
                "proposed_holdout_ic": round(avg_holdout, 6) if avg_holdout else None,
                "current_holdout_ic": None, "ic_delta": None,
                "rationale": f"Lens IC walk-forward as_of={as_of}, fwd={forward_days}d",
                "generator_version": "lens-calibration-v1",
            })
        except Exception:
            log.warning("lens_proposal_persist_failed", tier=tier, exc_info=True)
    log.info("lens_weight_proposals_persisted", n=len(proposals))


# -- backfill ---------------------------------------------------------------

def backfill_ic_journal(
    engine: Engine, start_date: date, end_date: date,
    forward_periods: list[int] | None = None,
    rolling_window_days: int = 252, step_days: int = 21,
) -> int:
    """Backfill IC over [start_date, end_date] in rolling windows. Returns rows written."""
    periods = forward_periods or [21, 63, 126]
    log.info("lens_ic_backfill_start", start=str(start_date), end=str(end_date),
             window=rolling_window_days, step=step_days)

    scores = _load_lens_scores(engine)
    if scores.empty:
        log.warning("backfill_no_scores"); return 0  # noqa: E702

    ret_cache = {}
    for fd in periods:
        rc = _FWD_MAP.get(fd)
        if rc:
            ret_cache[fd] = _load_fwd_returns(engine, rc)

    written = 0
    cursor = start_date + timedelta(days=rolling_window_days)
    while cursor <= end_date:
        ws = pd.Timestamp(cursor - timedelta(days=rolling_window_days))
        ce = pd.Timestamp(cursor)
        win_scores = scores[(scores["date"] >= ws) & (scores["date"] <= ce)]
        if win_scores.empty:
            cursor += timedelta(days=step_days); continue  # noqa: E702

        for fd in periods:
            rw = ret_cache.get(fd, pd.DataFrame())
            if rw.empty:
                continue
            win_ret = rw[(rw.index >= ws) & (rw.index <= ce)]
            if win_ret.empty:
                continue
            for lens in _LENSES:
                fac = _factor_frame(win_scores, lens)
                if fac.empty:
                    continue
                ic, qs, to = _compute_lens_ic(fac, win_ret)
                if ic.n_observations < 2:
                    continue
                persist_ic_result(
                    engine, signal_name=f"lens_{lens}", timeframe="daily",
                    forward_period_days=fd, rolling_window=f"{rolling_window_days}d",
                    as_of=cursor, result=ic,
                    quantile_spread_ann=_ann_spread(qs, fd), turnover_monthly=to,
                )
                written += 1
        cursor += timedelta(days=step_days)

    log.info("lens_ic_backfill_done", rows_written=written)
    return written
