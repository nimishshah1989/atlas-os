"""Point-in-time fundamental derivation — as-of TTM / YoY / ROE / D-E.

Turns an as-of panel of trailing quarters (income statement, from
``financials_quarterly``) plus the latest as-of annual row (balance sheet, from
``financials_annual``) into the scalar kwargs ``score_fundamental`` consumes. The
panel must already be: (a) filtered to ``period_end <= as_of − reporting_lag``,
(b) deduped consolidated-else-standalone, (c) sorted period_end DESC. This module
is PURE — no I/O — so it is unit-testable on real rows pulled from the DB.

Loop C (DECISIONS D10/D16): fundamentals now have real history — income to
2026-03 and a real balance sheet (equity/borrowings) — so ROE = PAT_ttm/equity
and D/E = total_borrowings/equity are genuine, not the old tv_metrics snapshot.
Metrics with no real source (ROA/ROIC/current/quick/gross) stay ``None`` and the
scorer's renorm drops them — never a fabricated stand-in (RULE #0).
"""
from __future__ import annotations

import bisect
from datetime import date, timedelta
from typing import Any

# Income-statement fields summed/averaged over the trailing window.
_TTM_Q = 4   # quarters in a trailing-twelve-month window
_YOY_Q = 8   # quarters needed to compare TTM vs year-ago TTM


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _ttm_sum(quarters: list[dict], field: str, lo: int, hi: int) -> float | None:
    """Sum *field* over quarters[lo:hi]; None if any of the window is missing."""
    if len(quarters) < hi:
        return None
    vals = [_num(quarters[i].get(field)) for i in range(lo, hi)]
    if any(v is None for v in vals):
        return None
    return sum(vals)


def derive_fundamentals_asof(
    quarters: list[dict[str, Any]],
    annual: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return ``score_fundamental`` kwargs + an evidence dict, from as-of inputs.

    ``quarters`` — trailing quarters (dedup, period_end DESC), each with at least
    revenue, ebit, pat, eps, net_margin, finance_costs, debt_equity_ratio.
    ``annual`` — latest as-of annual row with equity, total_borrowings (or None).
    """
    ev: dict[str, Any] = {"quarters_available": len(quarters)}
    out: dict[str, Any] = {
        "roe": None, "roa": None, "roic": None,
        "operating_margin": None, "net_margin": None, "gross_margin": None,
        "revenue_growth_yoy": None, "eps_growth_yoy": None,
        "debt_to_equity": None, "current_ratio": None, "quick_ratio": None,
        "revenue_ttm": None, "eps_diluted_ttm": None,
    }

    rev_ttm = _ttm_sum(quarters, "revenue", 0, _TTM_Q)
    pat_ttm = _ttm_sum(quarters, "pat", 0, _TTM_Q)
    ebit_ttm = _ttm_sum(quarters, "ebit", 0, _TTM_Q)
    eps_ttm = _ttm_sum(quarters, "eps", 0, _TTM_Q)
    out["revenue_ttm"] = rev_ttm
    out["eps_diluted_ttm"] = eps_ttm

    # Margins — prefer TTM; fall back to the latest reported quarter so a name with
    # <4 quarters still gets a margin reading (the value is real either way).
    if rev_ttm and rev_ttm > 0:
        if pat_ttm is not None:
            out["net_margin"] = pat_ttm / rev_ttm * 100.0
        if ebit_ttm is not None:
            out["operating_margin"] = ebit_ttm / rev_ttm * 100.0
        ev["margin_basis"] = "ttm"
    elif quarters:
        nm = _num(quarters[0].get("net_margin"))
        # net_margin in the feed is stored as a fraction (e.g. 0.07) — express as %.
        if nm is not None:
            out["net_margin"] = nm * 100.0 if abs(nm) <= 1.5 else nm
            ev["margin_basis"] = "latest_quarter"

    # Growth — TTM vs the year-ago TTM (needs 8 quarters).
    rev_prev = _ttm_sum(quarters, "revenue", _TTM_Q, _YOY_Q)
    eps_prev = _ttm_sum(quarters, "eps", _TTM_Q, _YOY_Q)
    if rev_ttm and rev_prev and rev_prev > 0:
        out["revenue_growth_yoy"] = (rev_ttm / rev_prev - 1.0) * 100.0
    if eps_ttm is not None and eps_prev is not None and eps_prev > 0:
        out["eps_growth_yoy"] = (eps_ttm / eps_prev - 1.0) * 100.0

    # Profitability + balance sheet — need the annual balance sheet (equity).
    equity = _num(annual.get("equity")) if annual else None
    if equity and equity > 0 and pat_ttm is not None:
        out["roe"] = pat_ttm / equity * 100.0
        ev["roe_basis"] = f"pat_ttm/{annual.get('period_end')}"
    elif annual is None:
        ev["profitability_reason"] = "missing"

    # Debt-to-equity — prefer the directly reported quarterly ratio (OneD context),
    # else total_borrowings / equity from the annual balance sheet.
    de_reported = _num(quarters[0].get("debt_equity_ratio")) if quarters else None
    if de_reported is not None and de_reported >= 0:
        out["debt_to_equity"] = de_reported
        ev["de_basis"] = "reported_quarterly"
    elif annual is not None:
        tb = _num(annual.get("total_borrowings"))
        if tb is not None and equity and equity > 0:
            out["debt_to_equity"] = tb / equity
            ev["de_basis"] = "borrowings/equity"
    if out["debt_to_equity"] is None and out["current_ratio"] is None:
        ev["balance_sheet_reason"] = "missing"

    # Deleveraging trajectory (evidence-only signal): falling finance costs across
    # the trailing window while revenue holds — the spec's "deleveraging" tell.
    fc_now = _ttm_sum(quarters, "finance_costs", 0, _TTM_Q)
    fc_prev = _ttm_sum(quarters, "finance_costs", _TTM_Q, _YOY_Q)
    if fc_now is not None and fc_prev is not None and fc_prev > 0:
        ev["finance_cost_yoy"] = round(fc_now / fc_prev - 1.0, 4)

    return {"kwargs": out, "evidence": ev}


# ── Step-function builder (historical backfill efficiency) ──────────────────
# The single-date derive above is fine for nightly, but the rebuild scores ~1,850
# dates. Rather than re-query/re-derive per date, precompute each instrument's
# fundamental kwargs as a STEP FUNCTION keyed by availability date: the as-of value
# only changes when a new quarter or annual filing becomes knowable (period_end +
# reporting_lag). For any scoring date D the as-of kwargs = the step whose
# availability ≤ D. Identical semantics to derive_fundamentals_asof, far fewer calls.

def _dedup_sort(records: list[dict], key_field: str = "period_end") -> list[dict]:
    """One row per period_end (prefer consolidated), ascending by period_end."""
    best: dict[Any, dict] = {}
    for r in records:
        pe = r.get(key_field)
        if pe is None:
            continue
        cur = best.get(pe)
        if cur is None or (bool(r.get("consolidated")) and not bool(cur.get("consolidated"))):
            best[pe] = r
    return [best[pe] for pe in sorted(best)]


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    return v.date() if hasattr(v, "date") else v


def build_fundamental_steps(
    quarters_by_iid: dict[Any, list[dict]],
    annual_by_iid: dict[Any, list[dict]],
    lag_q: int, lag_a: int,
) -> dict[Any, tuple[list[date], list[dict]]]:
    """Per-instrument (availability_dates, kwargs) step functions.

    availability_dates is ascending; kwargs[i] is the as-of fundamental kwargs that
    holds from availability_dates[i] until the next change point. Lookup with
    fundamental_asof_from_steps.
    """
    steps: dict[Any, tuple[list[date], list[dict]]] = {}
    all_iids = set(quarters_by_iid) | set(annual_by_iid)
    for iid in all_iids:
        q_sorted = _dedup_sort(quarters_by_iid.get(iid, []))
        a_sorted = _dedup_sort(annual_by_iid.get(iid, []))
        # availability dates (period_end + lag) for every filing
        q_avail = [(_as_date(r["period_end"]) + timedelta(days=lag_q), r) for r in q_sorted
                   if _as_date(r["period_end"]) is not None]
        a_avail = [(_as_date(r["period_end"]) + timedelta(days=lag_a), r) for r in a_sorted
                   if _as_date(r["period_end"]) is not None]
        change_points = sorted({cp for cp, _ in q_avail} | {cp for cp, _ in a_avail})
        if not change_points:
            continue
        avail_dates: list[date] = []
        kwargs_list: list[dict] = []
        for cp in change_points:
            # quarters knowable by cp, latest-first, capped at the YoY window
            q_known = [r for (av, r) in q_avail if av <= cp]
            # The nightly adapter (load_fundamental_data) only emits a fundamental row
            # for instruments that have ≥1 knowable QUARTER (it iterates the quarterly
            # panel). Mirror that: an annual filing alone (balance sheet, no income
            # statement) does NOT make a fundamental — skip such change points so the
            # backfill and the nightly path agree exactly.
            if not q_known:
                continue
            q_known_desc = list(reversed(q_known))[:_YOY_Q]
            a_known = [r for (av, r) in a_avail if av <= cp]
            annual = a_known[-1] if a_known else None
            derived = derive_fundamentals_asof(q_known_desc, annual)
            row = dict(derived["kwargs"]); row["instrument_id"] = iid
            avail_dates.append(cp)
            kwargs_list.append(row)
        steps[iid] = (avail_dates, kwargs_list)
    return steps


def fundamental_asof_from_steps(
    steps: dict[Any, tuple[list[date], list[dict]]], iid: Any, d: date,
) -> dict | None:
    """The as-of fundamental kwargs row for *iid* on date *d* (None if not yet knowable)."""
    entry = steps.get(iid)
    if not entry:
        return None
    avail_dates, kwargs_list = entry
    pos = bisect.bisect_right(avail_dates, d) - 1
    if pos < 0:
        return None
    return kwargs_list[pos]
