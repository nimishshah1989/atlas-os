#!/usr/bin/env python3
"""Backfill recent + medium-history fundamentals from Screener.in → staging.

Fills the gap NSE XBRL cannot (financials_quarterly stops at 2024-12-31 here): the
recent quarters (2025-03..2026-03) of P&L + the annual balance sheet (Equity/Reserves/
Borrowings → net worth, D/E). Writes into the SAME tables with source='SCREENER'.

RULE #0 guardrails (per the source-eval, 2026-06-21):
- basis (consolidated/standalone) is read from the page CAPTION, never the URL.
- every symbol is RECONCILED to XBRL on the latest overlap quarter (Screener net_profit
  must match XBRL pat within 2%); a divergent symbol is QUARANTINED, not written.
- XBRL wins on overlap — Screener only fills (period_end, consolidated) XBRL lacks.

Parser logic (regex HTML tables, no bs4) ported from
jip-data-engine/app/pipelines/fundamentals/screener_fetcher.py.

Run: python ingest_screener.py [--limit N] [--symbols A,B] [--universe 750|all] [--redo]
"""

from __future__ import annotations

import argparse
import re
import time
from calendar import monthrange
from datetime import UTC, date, datetime

import _db
import pandas as pd
import requests
from harness import STAGING_SCHEMA

M = STAGING_SCHEMA
_BASE = "https://www.screener.in"
_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://www.screener.in/",
}
_MONTH = {
    "Jan": "01",
    "Feb": "02",
    "Mar": "03",
    "Apr": "04",
    "May": "05",
    "Jun": "06",
    "Jul": "07",
    "Aug": "08",
    "Sep": "09",
    "Oct": "10",
    "Nov": "11",
    "Dec": "12",
}
_RECON_TOL = 0.02  # 2% on PAT at the overlap quarter

_PL_ROW_MAP = {
    "Sales": "revenue",
    "Revenue": "revenue",
    "Expenses": "total_expenses",
    "Operating Profit": "ebitda",
    "Other Income": "other_income",
    "Interest": "finance_costs",
    "Depreciation": "depreciation",
    "Profit before tax": "pbt",
    "Tax %": "tax_pct",
    "Net Profit": "pat",
    "EPS in Rs": "eps",
}
_BS_ROW_MAP = {
    "Equity Capital": "equity_capital",
    "Reserves": "reserves",
    "Borrowings": "total_borrowings",
    "Total Assets": "equity_and_liabilities",
}


# ── parser (ported from jip screener_fetcher; regex, no bs4) ──
def _date(s: str) -> date | None:
    if not s or s.strip() == "TTM":
        return None
    p = s.strip().split()
    if len(p) == 2 and p[0][:3] in _MONTH:
        y, m = int(p[1]), int(_MONTH[p[0][:3]])
        return date(y, m, monthrange(y, m)[1])
    return None


def _f(v) -> float | None:
    if v in (None, "", "--", "—"):
        return None
    try:
        c = str(v).replace(",", "").replace("%", "").strip()
        return float(c) if c else None
    except (ValueError, TypeError):
        return None


def _table(html: str, section: str) -> dict:
    pat = rf'id="{section}".*?(<table[^>]*class="data-table[^"]*".*?</table>)'
    m = re.search(pat, html, re.DOTALL)
    if not m:
        return {"headers": [], "rows": {}}
    t = m.group(1)
    out: dict = {"headers": [], "rows": {}}
    th = re.search(r"<thead>(.*?)</thead>", t, re.DOTALL)
    if th:
        out["headers"] = [
            re.sub(r"<.*?>", "", h).strip()
            for h in re.findall(r"<th[^>]*>(.*?)</th>", th.group(1), re.DOTALL)
        ]
    tb = re.search(r"<tbody>(.*?)</tbody>", t, re.DOTALL)
    if tb:
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tb.group(1), re.DOTALL):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", rm.group(1), re.DOTALL)
            if not cells:
                continue
            name = re.sub(r"&nbsp;", " ", re.sub(r"<[^>]+>", "", cells[0], flags=re.DOTALL))
            name = name.strip().rstrip("+").strip()
            if name:
                out["rows"][name] = [
                    re.sub(r"<[^>]+>", "", c, flags=re.DOTALL).strip() for c in cells[1:]
                ]
    return out


def _section_rows(html: str, section: str, row_map: dict, ptype: str) -> list[dict]:
    data = _table(html, section)
    cols = [(i, _date(h)) for i, h in enumerate(data["headers"]) if i and _date(h)]
    if not cols:
        return []
    by_date: dict = {d: {"period_end": d, "period_type": ptype} for _, d in cols}
    for name, vals in data["rows"].items():
        field = row_map.get(name)
        if not field:
            continue
        for ci, d in cols:
            j = ci - 1
            if 0 <= j < len(vals):
                by_date[d][field] = _f(vals[j])
    return list(by_date.values())


def _detect_basis(html: str) -> bool:
    """True=consolidated, False=standalone — from the table CAPTION, never the URL."""
    if re.search(r"Consolidated\s+Figures\s+in\s+Rs", html):
        return True
    return False  # 'Standalone Figures' or single-basis 'Figures in Rs'


# ── top-ratios panel (P/E, Book Value, ROE, ROCE, Market Cap, …) ──
# These are Screener.in's READY, point-in-time market ratios (the panel at the top
# of every company page). FM decision D1 (2026-06-25): ingest these ready ratios
# rather than derive — one consistent real source for the valuation + profitability
# lens inputs. RULE #0: every value parsed verbatim from the page; absent ⇒ None.
_RATIO_LABELS = {
    "Market Cap": "market_cap",
    "Current Price": "current_price",
    "Stock P/E": "stock_pe",
    "Book Value": "book_value",
    "ROCE": "roce",
    "ROE": "roe",
    "Dividend Yield": "div_yield",
    "Face Value": "face_value",
    "Debt to equity": "debt_to_equity",
    "EV/EBITDA": "ev_ebitda",
    "EV / EBITDA": "ev_ebitda",
}


def _top_ratios(html: str) -> dict:
    """Parse the #top-ratios <ul> into {field: float}. First .number per <li>
    (so 'High / Low' with two numbers contributes only its first, which we ignore).
    """
    m = re.search(r'<ul id="top-ratios">(.*?)</ul>', html, re.DOTALL)
    if not m:
        return {}
    out: dict = {}
    for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.DOTALL):
        nm = re.search(r'<span class="name">(.*?)</span>', li, re.DOTALL)
        if not nm:
            continue
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", nm.group(1))).strip()
        field = _RATIO_LABELS.get(label)
        if not field:
            continue
        num = re.search(r'<span class="number">(.*?)</span>', li, re.DOTALL)
        if num:
            out[field] = _f(num.group(1))
    # Derived: P/B = price ÷ book value (both real ready scalars). EV/EBITDA stays
    # whatever the panel exposed (None if absent — display-only, valuation 0% weight).
    px, bv = out.get("current_price"), out.get("book_value")
    out["pb"] = round(px / bv, 4) if (px and bv and bv != 0) else None
    return out


# ── fetch ──
_SESSION = None


def _session() -> requests.Session:
    """Warmed session — Screener serves DATA-LESS skeleton pages to cold/cookieless
    requests for many names; visiting the homepage first sets the cookies that
    unlock the full financial tables."""
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(_H)
        try:
            s.get(_BASE + "/", timeout=20)
        except Exception:
            pass
        _SESSION = s
    return _SESSION


def fetch(symbol: str, _retry: bool = True) -> tuple[str | None, bool]:
    """Return (html, is_consolidated). Requires a FULL page (has `data-date-key`,
    the period columns) — a skeleton without it is rejected and retried with a
    fresh warm session (handles Screener's intermittent stripping)."""
    s = _session()
    for suffix in ("consolidated/", ""):
        try:
            r = s.get(f"{_BASE}/company/{symbol}/{suffix}", timeout=25)
        except Exception:
            continue
        if r.status_code == 200 and "data-date-key" in r.text:
            return r.text, _detect_basis(r.text)
    if _retry:  # got a skeleton / failure — re-warm once and retry
        global _SESSION
        _SESSION = None
        time.sleep(2)
        return fetch(symbol, _retry=False)
    return None, False


def ddl() -> None:
    _db.exec_script(f"""
    create table if not exists {M}.screener_state (
        instrument_id uuid primary key, symbol text not null, status text not null,
        quarters integer, annuals integer, note text,
        updated_at timestamptz not null default now()
    );""")
    # One-row-per-instrument snapshot of Screener's ready market ratios. Justified
    # standalone table (not sprawl): single small (~498-row) PIT snapshot the lens
    # adapter LEFT JOINs by instrument_id; nothing else fits its shape (these are
    # market-ratios, not period-end fundamentals, so they don't belong on the
    # quarterly/annual rows). Source-stamped for the frontend's Screener.in chip.
    _db.exec_script(f"""
    create table if not exists {M}.screener_ratios (
        instrument_id uuid primary key, symbol text not null,
        stock_pe numeric, pb numeric, ev_ebitda numeric, roe numeric, roce numeric,
        market_cap numeric, book_value numeric, current_price numeric,
        div_yield numeric, debt_to_equity numeric,
        as_of date not null, source text not null default 'SCREENER',
        updated_at timestamptz not null default now()
    );""")


def _quarterly_rows(iid, symbol, consol, rows) -> list[dict]:
    out = []
    for r in rows:
        if r.get("period_type") != "quarterly":
            continue
        rev, pat = r.get("revenue"), r.get("pat")
        if rev is None and pat is None:
            continue
        fc, pbt = r.get("finance_costs"), r.get("pbt")
        ebitda = r.get("ebitda")
        ebit = (pbt + fc) if (pbt is not None and fc is not None) else None
        tax = (
            round(pbt * r["tax_pct"] / 100, 4)
            if (pbt is not None and r.get("tax_pct") is not None)
            else None
        )
        out.append(
            {
                "instrument_id": iid,
                "symbol": symbol,
                "period_end": r["period_end"],
                "consolidated": consol,
                "revenue": rev,
                "other_income": r.get("other_income"),
                "total_expenses": r.get("total_expenses"),
                "finance_costs": fc,
                "depreciation": r.get("depreciation"),
                "ebit": ebit,
                "ebitda": ebitda,
                "pbt": pbt,
                "tax": tax,
                "pat": pat,
                "eps": r.get("eps"),
                "ebitda_margin": round(ebitda / rev, 4) if (ebitda and rev) else None,
                "net_margin": round(pat / rev, 4) if (pat and rev) else None,
                "source": "SCREENER",
            }
        )
    return out


def _annual_rows(iid, symbol, consol, rows) -> list[dict]:
    out = []
    for r in rows:
        if r.get("period_type") != "annual":
            continue
        eqc, res = r.get("equity_capital"), r.get("reserves")
        equity = (eqc or 0) + (res or 0) if (eqc is not None or res is not None) else None
        tb = r.get("total_borrowings")
        if equity is None and tb is None:
            continue
        out.append(
            {
                "instrument_id": iid,
                "symbol": symbol,
                "period_end": r["period_end"],
                "consolidated": consol,
                "equity": equity,
                "total_borrowings": tb,
                "equity_and_liabilities": r.get("equity_and_liabilities"),
                "source": "SCREENER",
            }
        )
    return out


def _reconciles(iid, consol, q_rows) -> tuple[bool, str]:
    """Screener PAT must match XBRL PAT within tol on the latest overlap quarter."""
    xbrl = _db.read_df(
        f"select period_end, pat from {M}.financials_quarterly "
        "where instrument_id=:i and consolidated=:c and source='NSE_XBRL' and pat is not null",
        {"i": iid, "c": consol},
    )
    if xbrl.empty:
        return True, "no_xbrl_overlap"  # nothing to reconcile against; accept (it's a fill)
    xmap = {r.period_end: float(r.pat) for r in xbrl.itertuples()}
    for row in q_rows:
        pe = row["period_end"]
        if pe in xmap and row["pat"] is not None:
            xp, sp = xmap[pe], float(row["pat"])
            if xp == 0:
                continue
            # Combined tolerance: 2% relative OR ₹1cr absolute. Screener displays
            # whole crores, so on small-caps a ±0.5cr rounding blows past a pure
            # relative bound while the value is genuinely correct.
            if abs(sp - xp) <= max(_RECON_TOL * abs(xp), 1.0):
                return True, f"ok@{pe} screener={sp} xbrl={xp}"
            return False, f"DIVERGE@{pe} screener={sp} xbrl={xp} (Δ{abs(sp - xp):.1f}cr)"
    return True, "no_shared_quarter"  # overlap exists but no shared quarter w/ pat; accept


def _existing_periods(iid, table, consol) -> set:
    df = _db.read_df(
        f"select period_end from {M}.{table} where instrument_id=:i and consolidated=:c",
        {"i": iid, "c": consol},
    )
    return {r.period_end for r in df.itertuples()}


def _store_ratios(iid: str, symbol: str, html: str) -> bool:
    """Parse + upsert the Screener top-ratios snapshot. Returns True if any captured."""
    r = _top_ratios(html)
    if not any(r.get(k) is not None for k in ("stock_pe", "roe", "roce", "pb", "book_value")):
        return False
    row = {
        "instrument_id": iid,
        "symbol": symbol,
        "stock_pe": r.get("stock_pe"),
        "pb": r.get("pb"),
        "ev_ebitda": r.get("ev_ebitda"),
        "roe": r.get("roe"),
        "roce": r.get("roce"),
        "market_cap": r.get("market_cap"),
        "book_value": r.get("book_value"),
        "current_price": r.get("current_price"),
        "div_yield": r.get("div_yield"),
        "debt_to_equity": r.get("debt_to_equity"),
        "as_of": date.today(),
        "source": "SCREENER",
    }
    _db.upsert_df(f"{M}.screener_ratios", pd.DataFrame([row]), ["instrument_id"])
    return True


def ingest_symbol(iid: str, symbol: str) -> tuple[int, int, str]:
    html, consol = fetch(symbol)
    if not html:
        return 0, 0, "fetch_failed"
    _store_ratios(iid, symbol, html)
    rows = (
        _section_rows(html, "quarters", _PL_ROW_MAP, "quarterly")
        + _section_rows(html, "profit-loss", _PL_ROW_MAP, "annual")
        + _section_rows(html, "balance-sheet", _BS_ROW_MAP, "annual")
    )
    q = _quarterly_rows(iid, symbol, consol, rows)
    a = _annual_rows(iid, symbol, consol, rows)
    ok, note = _reconciles(iid, consol, q)
    if not ok:
        return 0, 0, f"quarantined:{note}"
    # XBRL wins on overlap — only insert periods XBRL lacks
    have_q = _existing_periods(iid, "financials_quarterly", consol)
    have_a = _existing_periods(iid, "financials_annual", consol)
    q = [r for r in q if r["period_end"] not in have_q]
    a = [r for r in a if r["period_end"] not in have_a]
    nq = (
        _db.upsert_df(
            f"{M}.financials_quarterly",
            pd.DataFrame(q),
            ["instrument_id", "period_end", "consolidated"],
        )
        if q
        else 0
    )
    na = (
        _db.upsert_df(
            f"{M}.financials_annual",
            pd.DataFrame(a),
            ["instrument_id", "period_end", "consolidated"],
        )
        if a
        else 0
    )
    return nq, na, note


def targets(universe: str, only_pending: bool, limit, symbols):
    if symbols:
        df = _db.read_df(
            f"select instrument_id, symbol from {M}.instrument_master where symbol = any(:s)",
            {"s": symbols},
        )
    elif universe == "750":
        df = _db.read_df("""select instrument_id, symbol from foundation_staging.instrument_master
            where asset_class='stock' and kite_token is not null and is_active
            order by symbol""")
    else:
        df = _db.read_df(
            f"select instrument_id, symbol from {M}.instrument_master "
            "where asset_class='stock' and kite_token is not null order by symbol"
        )
    df["instrument_id"] = df["instrument_id"].astype(str)
    if only_pending:
        done = _db.read_df(f"select instrument_id from {M}.screener_state where status='done'")
        df = df[~df["instrument_id"].isin(set(done["instrument_id"].astype(str)))]
    return df.head(limit) if limit else df


def run(universe="750", only_pending=True, limit=None, symbols=None) -> dict:
    ddl()
    tgt = targets(universe, only_pending, limit, symbols)
    total = len(tgt)
    done = quar = err = 0
    qtot = atot = 0
    print(f"[screener] targets={total}", flush=True)
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, sym = r.instrument_id, r.symbol
        try:
            nq, na, note = ingest_symbol(iid, sym)
            status = "quarantined" if note.startswith("quarantined") else "done"
            if status == "quarantined":
                quar += 1
            else:
                done += 1
                qtot += nq
                atot += na
            _db.upsert_df(
                f"{M}.screener_state",
                pd.DataFrame(
                    [
                        {
                            "instrument_id": iid,
                            "symbol": sym,
                            "status": status,
                            "quarters": nq,
                            "annuals": na,
                            "note": note[:200],
                            "updated_at": datetime.now(UTC),
                        }
                    ]
                ),
                ["instrument_id"],
            )
        except Exception as e:
            err += 1
            _db.upsert_df(
                f"{M}.screener_state",
                pd.DataFrame(
                    [
                        {
                            "instrument_id": iid,
                            "symbol": sym,
                            "status": "error",
                            "quarters": None,
                            "annuals": None,
                            "note": repr(e)[:200],
                            "updated_at": datetime.now(UTC),
                        }
                    ]
                ),
                ["instrument_id"],
            )
        if n % 20 == 0 or n == total:
            print(
                f"[screener] {n}/{total} done={done} quar={quar} err={err} "
                f"q={qtot} a={atot} last={sym}",
                flush=True,
            )
        time.sleep(1.0)  # polite: ~1 req/s
    print(
        f"[screener] COMPLETE done={done} quarantined={quar} err={err} quarters={qtot} annuals={atot}",
        flush=True,
    )
    return {
        "targets": total,
        "done": done,
        "quarantined": quar,
        "err": err,
        "quarters": qtot,
        "annuals": atot,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--symbols", type=lambda s: s.split(","))
    ap.add_argument("--universe", choices=["750", "all"], default="750")
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    run(universe=a.universe, only_pending=not a.redo, limit=a.limit, symbols=a.symbols)


if __name__ == "__main__":
    main()
