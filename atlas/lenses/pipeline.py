"""Six-lens scoring pipeline — orchestrates all scorers for all instruments.

Called by nightly cron or ad-hoc. Loads data, scores each instrument across
all 6 lenses, computes composite + conviction, writes to atlas_lens_scores_daily.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.db import get_engine, load_thresholds
from atlas.lenses.compute.catalyst import score_catalyst
from atlas.lenses.compute.composite import compute_composite
from atlas.lenses.compute.flow import score_flow
from atlas.lenses.compute.fundamental import score_fundamental
from atlas.lenses.compute.policy import score_policy
from atlas.lenses.compute.risk_flags import compute_risk_flags
from atlas.lenses.compute.technical import score_technical
from atlas.lenses.compute.thresholds_view import nest_thresholds
from atlas.lenses.compute.valuation import score_valuation
from atlas.lenses.data.adapters import (
    is_trading_day,
    latest_trading_day,
    load_catalyst_data,
    load_flow_data,
    load_fundamental_data,
    load_instrument_sectors,
    load_policy_registry,
    load_technical_data,
    purge_stale_lens_scores,
    write_lens_scores,
)

log = structlog.get_logger()
_IST = ZoneInfo("Asia/Kolkata")


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _dec_or_none(v: Any) -> float | None:
    """Convert Decimal/float to float for JSON serialization."""
    if v is None:
        return None
    return float(v)


def _g(obj: Any, attr: str) -> float | None:
    """Shorthand: extract attr from a scorer result, converting to float."""
    return _dec_or_none(getattr(obj, attr)) if obj else None


def _group_by_iid(df: Any, sort_col: str | None = None) -> dict:
    """Group a DataFrame by instrument_id into dict of record-lists."""
    if df is None or df.empty:
        return {}
    out = {}
    for iid, grp in df.groupby("instrument_id"):
        if sort_col:
            grp = grp.sort_values(sort_col, ascending=False)
        out[iid] = grp.to_dict("records")
    return out


def run_pipeline(
    as_of: date | None = None,
    engine: Engine | None = None,
    batch_size: int = 500,
) -> dict[str, Any]:
    """Run the full six-lens scoring pipeline."""
    eng = engine or get_engine()
    # Resolve the run date from the real NSE trading calendar — never wall-clock
    # date.today() (which on a weekend/holiday would score a non-trading day from
    # stale/empty feeds). With no as_of, snap to the latest real session; with an
    # explicit as_of, refuse anything that is not an NSE session.
    if as_of is None:
        dt = latest_trading_day(eng)
    elif is_trading_day(eng, as_of):
        dt = as_of
    else:
        raise ValueError(
            f"{as_of} is not an NSE trading day (absent from the NIFTY 50 "
            "calendar); refusing to score a non-trading day"
        )
    run_id = uuid.uuid4()
    log.info("lens_run_date_resolved", requested=str(as_of), resolved=str(dt))
    thresholds = load_thresholds(engine=eng)
    th = {k: float(v) if isinstance(v, Decimal) else v for k, v in thresholds.items()}
    # Build the nested shapes compute_composite reads (lens_weights / conviction_tiers /
    # convergence) from the FLAT DB keys, so the DB / IC-learned weights are actually
    # consumed instead of the composite's hard-coded fallback (Loop C blocker 0a, D8).
    th = nest_thresholds(th)

    log.info("lens_pipeline_start", as_of=str(dt), run_id=str(run_id))
    tech_df = load_technical_data(eng, dt)
    fund_df = load_fundamental_data(eng, dt)
    cat_df = load_catalyst_data(eng, as_of=dt)
    flow_data = load_flow_data(eng, as_of=dt)
    policies = load_policy_registry(eng)
    sectors_df = load_instrument_sectors(eng)

    log.info("lens_data_loaded",
             tech=len(tech_df), fund=len(fund_df),
             cat=len(cat_df), flow_insider=len(flow_data["insider"]),
             policies=len(policies), instruments=len(sectors_df))

    results, scored, skipped = score_all(
        dt, tech_df, fund_df, cat_df, flow_data, sectors_df, policies, th, run_id)

    write_lens_scores(eng, results, run_id)

    # Remove rows for this date left by an EARLIER run (universe shrink / re-run)
    # so the journal equals exactly this run's scored universe. GUARD: never purge
    # when 0 scored — a total failure must not wipe a previously-good journal day.
    if scored > 0:
        purged = purge_stale_lens_scores(eng, dt, run_id, asset_class="stock")
    else:
        purged = 0
        log.error("lens_pipeline_zero_scored_no_purge", as_of=str(dt),
                  skipped=skipped, msg="0 instruments scored; skipping purge to "
                  "protect the existing journal for this date")

    summary = {
        "as_of": str(dt), "run_id": str(run_id),
        "instruments_scored": scored, "instruments_skipped": skipped,
        "total_instruments": len(sectors_df), "stale_rows_purged": purged,
    }
    log.info("lens_pipeline_complete", **summary)
    return summary


def _cell(idx: Any, iid: Any, col: str) -> Any:
    """Single cell from a (possibly duplicate-index) frame; None if absent."""
    if idx is None or getattr(idx, "empty", True) or iid not in idx.index or col not in idx.columns:
        return None
    v = idx.loc[iid, col]
    return v.iloc[0] if hasattr(v, "iloc") else v


def _row(idx: Any, iid: Any) -> Any:
    """The row Series for *iid*; None if absent. Collapses duplicate index to first."""
    if idx is None or getattr(idx, "empty", True) or iid not in idx.index:
        return None
    r = idx.loc[iid]
    return r.iloc[0] if isinstance(r, pd.DataFrame) else r


def _sector_median_pe(tech_idx: Any, fund_idx: Any, sector_of: dict) -> tuple[dict, dict]:
    """As-of PE per instrument (close_raw ÷ TTM EPS) → cross-sectional sector medians.

    This is the PIT replacement for the old tv_metrics sector-median CTE: PE is
    rebuilt for each historical date from that day's real close and the as-of TTM
    EPS, then the median is taken across the stocks actually present in each sector
    on that date.
    """
    import statistics
    pe_by_iid: dict[Any, float] = {}
    sector_pes: dict[str, list[float]] = {}
    if tech_idx is None or fund_idx is None or getattr(tech_idx, "empty", True) or getattr(fund_idx, "empty", True):
        return pe_by_iid, {}
    for iid in fund_idx.index:
        close_raw = _to_float(_cell(tech_idx, iid, "close_raw"))
        eps = _to_float(_cell(fund_idx, iid, "eps_diluted_ttm"))
        if close_raw and eps and eps > 0:
            pe = close_raw / eps
            pe_by_iid[iid] = pe
            s = sector_of.get(iid)
            if s and 0 < pe < 500:
                sector_pes.setdefault(s, []).append(pe)
    medians = {s: statistics.median(v) for s, v in sector_pes.items() if v}
    return pe_by_iid, medians


def score_all(
    dt: date, tech_df: Any, fund_df: Any, cat_df: Any, flow_data: dict,
    sectors_df: Any, policies: list, th: dict[str, Any], run_id: uuid.UUID,
) -> tuple[list[dict[str, Any]], int, int]:
    """Score the whole stock universe for one date from PRELOADED frames.

    Shared by run_pipeline (nightly: per-date adapter loads) and the historical
    backfill (per-date slices of preloaded chunk panels) so both paths emit
    identical PIT output. Returns (results, scored, skipped)."""
    tech_idx = tech_df.set_index("instrument_id") if (tech_df is not None and not tech_df.empty) else pd.DataFrame()
    fund_idx = fund_df.set_index("instrument_id") if (fund_df is not None and not fund_df.empty) else pd.DataFrame()
    cat_by_iid = _group_by_iid(cat_df)
    insider_by_iid = _group_by_iid(flow_data["insider"])
    sh_by_iid = _group_by_iid(flow_data["shareholding"], sort_col="period_end")
    bulk_by_iid = _group_by_iid(flow_data["bulk_deals"])

    sector_of = (dict(zip(sectors_df["instrument_id"], sectors_df["sector"]))
                 if "sector" in sectors_df.columns else {})
    pe_by_iid, sector_median = _sector_median_pe(tech_idx, fund_idx, sector_of)

    results: list[dict[str, Any]] = []
    scored, skipped = 0, 0
    for _, row in sectors_df.iterrows():
        iid = row["instrument_id"]
        symbol = row.get("symbol", "")
        try:
            # Technical (PIT: price=adjusted close on dt; ATR/BB/vol_ratio/pos_52w/
            # rs_*_sector from technical_daily on dt).
            t = _row(tech_idx, iid)
            tech_result = score_technical(
                ema_21=_to_float(t.get("ema_21")), ema_50=_to_float(t.get("ema_50")),
                ema_200=_to_float(t.get("ema_200")), rsi_14=_to_float(t.get("rsi_14")),
                price=_to_float(t.get("price_adj")), ret_1w=_to_float(t.get("ret_1w")),
                rs_1m_n500=_to_float(t.get("rs_1m_n500")), rs_3m_n500=_to_float(t.get("rs_3m_n500")),
                rs_6m_n500=_to_float(t.get("rs_6m_n500")), rs_12m_n500=_to_float(t.get("rs_12m_n500")),
                atr_14=_to_float(t.get("atr_14")), bb_width=_to_float(t.get("bb_width")),
                vol_ratio_30d=_to_float(t.get("vol_ratio_30d")),
                vol_ratio_60d=_to_float(t.get("vol_ratio_60d")),
                pos_52w=_to_float(t.get("pos_52w")),
                rs_1m_sector=_to_float(t.get("rs_1m_sector")),
                rs_3m_sector=_to_float(t.get("rs_3m_sector")),
                rs_6m_sector=_to_float(t.get("rs_6m_sector")),
                rs_12m_sector=_to_float(t.get("rs_12m_sector")),
                thresholds=th,
            ) if t is not None else None

            # Fundamental (PIT: TTM/YoY/ROE/D-E from as-of quarters + annual).
            f = _row(fund_idx, iid)
            fund_result = score_fundamental(
                roe=_to_float(f.get("roe")), roa=_to_float(f.get("roa")), roic=_to_float(f.get("roic")),
                operating_margin=_to_float(f.get("operating_margin")), net_margin=_to_float(f.get("net_margin")),
                gross_margin=_to_float(f.get("gross_margin")),
                revenue_growth_yoy=_to_float(f.get("revenue_growth_yoy")),
                eps_growth_yoy=_to_float(f.get("eps_growth_yoy")),
                debt_to_equity=_to_float(f.get("debt_to_equity")),
                current_ratio=_to_float(f.get("current_ratio")), quick_ratio=_to_float(f.get("quick_ratio")),
                revenue_ttm=_to_float(f.get("revenue_ttm")), eps_diluted_ttm=_to_float(f.get("eps_diluted_ttm")),
                thresholds=th,
            ) if f is not None else None

            # Valuation (PIT: PE = close ÷ TTM EPS; as-of cross-sectional sector median;
            # pb/ev have no unit-safe as-of source -> None).
            val_result = score_valuation(
                pe_ttm=pe_by_iid.get(iid), pb_fbs=None, ev_ebitda=None,
                price=_to_float(t.get("close_raw")),
                pos_52w=_to_float(t.get("pos_52w")), ema_200=_to_float(t.get("ema_200")),
                sector_median_pe=sector_median.get(sector_of.get(iid)), thresholds=th,
            ) if t is not None else None

            # Catalyst (already as-of via load_catalyst_data).
            filings = cat_by_iid.get(iid, [])
            cat_result = score_catalyst(filings, dt, th) if filings else None

            # Flow (already as-of via load_flow_data).
            insider_txns = insider_by_iid.get(iid, [])
            sh_records = sh_by_iid.get(iid, [])
            sh_current = sh_records[0] if len(sh_records) >= 1 else None
            sh_previous = sh_records[1] if len(sh_records) >= 2 else None
            bulk_deals = bulk_by_iid.get(iid, [])
            flow_result = score_flow(
                insider_txns, sh_current, sh_previous, bulk_deals, th,
            ) if (insider_txns or sh_current or bulk_deals) else None

            pol_result = score_policy(row.get("sector"), row.get("industry"), policies, th)

            risk_result = compute_risk_flags(
                insider_signals=insider_txns, quarterly_margins=[], annual_financials={},
                filings=filings,
                price=_to_float(t.get("price_adj")) if t is not None else None,
                ema_200=_to_float(t.get("ema_200")) if t is not None else None,
                thresholds=th,
            )

            comp_result = compute_composite(
                technical=_dec_or_none(tech_result.score) if tech_result else None,
                fundamental=_dec_or_none(fund_result.score) if fund_result else None,
                valuation_score=_dec_or_none(val_result.score) if val_result else None,
                catalyst=_dec_or_none(cat_result.score) if cat_result else None,
                flow=_dec_or_none(flow_result.score) if flow_result else None,
                policy=_dec_or_none(pol_result.score) if pol_result else None,
                valuation_multiplier=float(val_result.multiplier) if val_result else 1.0,
                smart_money_score=float(flow_result.smart_money) if flow_result and flow_result.smart_money else 0.0,
                degradation_score=float(risk_result.degradation_score),
                thresholds=th,
            )

            result = _build_result(
                iid, dt, tech_idx, tech_result, fund_result, val_result,
                cat_result, flow_result, pol_result, comp_result, risk_result, run_id,
            )
            results.append(result)
            scored += 1
        except Exception:
            log.exception("lens_score_error", instrument_id=str(iid), symbol=symbol)
            skipped += 1

    return results, scored, skipped


def _build_result(
    iid: Any, dt: date, tech_idx: Any,
    tech_result: Any, fund_result: Any, val_result: Any,
    cat_result: Any, flow_result: Any, pol_result: Any,
    comp_result: Any, risk_result: Any, run_id: uuid.UUID,
) -> dict[str, Any]:
    """Assemble the flat result dict for one instrument."""
    tr, fr, vr, cr, flr, pr = tech_result, fund_result, val_result, cat_result, flow_result, pol_result
    asset = tech_idx.loc[iid].get("asset_class", "stock") if iid in tech_idx.index else "stock"
    sm = _g(flr, "smart_money") if flr and flr.smart_money else 0.0
    return {
        "instrument_id": iid, "date": dt, "asset_class": asset,
        # Lens headline scores
        "technical": _g(tr, "score"), "fundamental": _g(fr, "score"),
        "valuation": _g(vr, "score"), "catalyst": _g(cr, "score"),
        "flow": _g(flr, "score"), "policy": _g(pr, "score"),
        # Technical sub
        "tech_trend": _g(tr, "trend"), "tech_rs": _g(tr, "relative_strength"),
        "tech_vol_contraction": _g(tr, "vol_contraction"), "tech_volume": _g(tr, "volume"),
        # Fundamental sub
        "fund_profitability": _g(fr, "profitability"), "fund_margin": _g(fr, "margin"),
        "fund_growth": _g(fr, "growth"), "fund_balance_sheet": _g(fr, "balance_sheet"),
        "fund_op_leverage": _g(fr, "op_leverage"),
        # Valuation sub
        "val_pe_vs_sector": _g(vr, "pe_vs_sector"), "val_absolute_pe": _g(vr, "absolute_pe"),
        "val_pb": _g(vr, "price_to_book"), "val_ev_ebitda": _g(vr, "ev_ebitda"),
        "val_52w_position": _g(vr, "position_52w"),
        # Catalyst sub
        "cat_earnings_strategy": _g(cr, "earnings_strategy"),
        "cat_capital_action": _g(cr, "capital_action"), "cat_governance": _g(cr, "governance"),
        # Flow sub
        "flow_promoter": _g(flr, "promoter"), "flow_institutional": _g(flr, "institutional"),
        "flow_smart_money": _g(flr, "smart_money"),
        # Policy sub
        "policy_tailwind": _g(pr, "tailwind"),
        # Composite & meta
        "composite": _dec_or_none(comp_result.final_score),
        "conviction_tier": comp_result.conviction_tier,
        # No valuation row at all -> 'UNKNOWN' (matches the scorer's no-data
        # contract); never the misleading 'FAIR' label for a name we can't value.
        "valuation_zone": vr.zone if vr else "UNKNOWN",
        "valuation_multiplier": _dec_or_none(vr.multiplier) if vr else 1.0,
        "smart_money_score": sm, "degradation_score": _dec_or_none(risk_result.degradation_score),
        "risk_flags": json.dumps(list(risk_result.flags)),
        "evidence": json.dumps(comp_result.evidence),
        "lenses_active": comp_result.lenses_active,
        "coverage_factor": _dec_or_none(comp_result.coverage_factor),
        "compute_run_id": run_id, "computed_at": datetime.now(_IST),
    }
