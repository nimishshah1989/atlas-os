#!/usr/bin/env python3
"""Backfill quarterly financials from NSE XBRL → staging (resumable, self-healing).

Proven path (probed 2026-06-20): seed NSE cookies → corporates-financial-results API
returns per-quarter records with a cookie-free `xbrl` URL on nsearchives → parse the
unified Ind-AS taxonomy. The standalone quarter is the `OneD` context (verified:
RELIANCE Q3FY25 revenue ₹128,260 Cr / PAT ₹8,721 Cr / EPS 6.44).

Powers the Fundamental lens's trend signals (margin/EBITDA/growth quarterly).
Resumable via xbrl_state; safe to kill/restart (the tmux loop does exactly that on
cookie expiry / crashes). Run: python ingest_xbrl.py [--limit N] [--redo]
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests

import _db
from harness import STAGING_SCHEMA

M = STAGING_SCHEMA
_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0",
      "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
      "Referer": "https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE"}
_API = "https://www.nseindia.com/api/corporates-financial-results"
# in-bse-fin concept (local tag) → our column. Standalone-quarter context = 'OneD'.
_TAGS = {
    "RevenueFromOperations": "revenue", "OtherIncome": "other_income",
    "Income": "total_income", "Expenses": "total_expenses",
    "FinanceCosts": "finance_costs",
    "DepreciationDepletionAndAmortisationExpense": "depreciation",
    "ProfitBeforeTax": "pbt", "TaxExpense": "tax", "ProfitLossForPeriod": "pat",
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": "eps",
    "InterestEarned": "interest_earned",  # banks/NBFC revenue proxy
}
# Disclosed ratios in the quarterly filing (OneD context) — NOT monetary, no ₹-crore scaling.
_RATIO_TAGS = {"DebtEquityRatio": "debt_equity_ratio",
               "DebtServiceCoverageRatio": "debt_service_coverage"}
# Paid-up equity capital (OneD, monetary → crore).
_TAGS["PaidUpValueOfEquityShareCapital"] = "paid_up_equity_capital"
_QTR_CTX = "OneD"

# Balance-sheet concepts from the ANNUAL/half-yearly filing (OneI = instant context).
# Monetary (₹ → crore). Equity = total shareholders' equity (→ ROE); Borrowings = total debt.
_BS_TAGS = {"Equity": "equity", "BorrowingsNoncurrent": "borrowings_noncurrent",
            "BorrowingsCurrent": "borrowings_current",
            "TradePayablesCurrent": "trade_payables_current",
            "TradePayablesNoncurrent": "trade_payables_noncurrent",
            "EquityAndLiabilities": "equity_and_liabilities"}
_BS_CTX = "OneI"


def ddl() -> None:
    _db.exec_script(f"""
    create table if not exists {M}.financials_quarterly (
        instrument_id uuid not null, symbol text not null,
        period_end date not null, consolidated boolean not null,
        revenue numeric, other_income numeric, total_income numeric,
        total_expenses numeric, finance_costs numeric, depreciation numeric,
        ebit numeric, ebitda numeric, pbt numeric, tax numeric, pat numeric,
        eps numeric, ebitda_margin numeric, net_margin numeric,
        is_bank boolean, seq_number bigint, xbrl_url text,
        source text not null default 'NSE_XBRL', ingested_at timestamptz not null default now(),
        primary key (instrument_id, period_end, consolidated)
    );
    -- quarterly disclosed ratios + equity capital (parsed from the OneD context)
    alter table {M}.financials_quarterly add column if not exists debt_equity_ratio numeric;
    alter table {M}.financials_quarterly add column if not exists debt_service_coverage numeric;
    alter table {M}.financials_quarterly add column if not exists paid_up_equity_capital numeric;
    -- FULL balance sheet (annual/half-yearly filing, OneI context) → ROE / real D-E history
    create table if not exists {M}.financials_annual (
        instrument_id uuid not null, symbol text not null,
        period_end date not null, consolidated boolean not null,
        equity numeric, borrowings_noncurrent numeric, borrowings_current numeric,
        total_borrowings numeric, trade_payables_current numeric,
        trade_payables_noncurrent numeric, equity_and_liabilities numeric,
        seq_number bigint, xbrl_url text,
        source text not null default 'NSE_XBRL', ingested_at timestamptz not null default now(),
        primary key (instrument_id, period_end, consolidated)
    );
    create table if not exists {M}.xbrl_state (
        instrument_id uuid not null, symbol text not null, status text not null,
        quarters integer, error text, updated_at timestamptz not null default now(),
        primary key (instrument_id)
    );
    alter table {M}.xbrl_state add column if not exists annuals integer;
    """)


def session() -> requests.Session:
    s = requests.Session(); s.headers.update(_H)
    s.get("https://www.nseindia.com/", timeout=20)
    s.get("https://www.nseindia.com/option-chain", timeout=20)
    return s


def list_filings(s: requests.Session, symbol: str, period: str) -> list[dict]:
    r = s.get(_API, params={"index": "equities", "symbol": symbol, "period": period}, timeout=30)
    r.raise_for_status()
    return r.json()


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_xbrl(xml: bytes) -> dict:
    root = ET.fromstring(xml)
    ln = lambda t: t.split("}")[-1]
    out: dict = {}
    ratios: dict = {}
    for el in root.iter():
        name = ln(el.tag)
        if el.get("contextRef") != _QTR_CTX or not (el.text and el.text.strip()):
            continue
        if name in _TAGS:
            out[_TAGS[name]] = _num(el.text.strip())
        elif name in _RATIO_TAGS:  # ratios are unitless — do NOT scale
            ratios[_RATIO_TAGS[name]] = _num(el.text.strip())
    cr = 1e7  # rupees → ₹ crore
    rev = out.get("revenue") or out.get("interest_earned")
    fc, dep, pbt, pat = out.get("finance_costs"), out.get("depreciation"), out.get("pbt"), out.get("pat")
    ebit = (pbt + fc) if (pbt is not None and fc is not None) else None
    ebitda = (ebit + dep) if (ebit is not None and dep is not None) else None
    def c(v): return round(v / cr, 4) if v is not None else None
    return {
        "revenue": c(rev), "other_income": c(out.get("other_income")),
        "total_income": c(out.get("total_income")), "total_expenses": c(out.get("total_expenses")),
        "finance_costs": c(fc), "depreciation": c(dep), "ebit": c(ebit), "ebitda": c(ebitda),
        "pbt": c(pbt), "tax": c(out.get("tax")), "pat": c(pat), "eps": out.get("eps"),
        "ebitda_margin": round(ebitda / rev, 4) if (ebitda and rev) else None,
        "net_margin": round(pat / rev, 4) if (pat and rev) else None,
        "paid_up_equity_capital": c(out.get("paid_up_equity_capital")),
        **ratios,
    }


def parse_balance_sheet(xml: bytes) -> dict:
    """Parse the OneI (instant) balance-sheet context from an annual/half-yearly filing."""
    root = ET.fromstring(xml)
    ln = lambda t: t.split("}")[-1]
    out: dict = {}
    for el in root.iter():
        name = ln(el.tag)
        if name in _BS_TAGS and el.get("contextRef") == _BS_CTX and el.text and el.text.strip():
            out.setdefault(_BS_TAGS[name], _num(el.text.strip()))  # first = current-year column
    cr = 1e7
    def c(v): return round(v / cr, 4) if v is not None else None
    bnc, bc = out.get("borrowings_noncurrent"), out.get("borrowings_current")
    total_b = (bnc or 0) + (bc or 0) if (bnc is not None or bc is not None) else None
    return {
        "equity": c(out.get("equity")), "borrowings_noncurrent": c(bnc),
        "borrowings_current": c(bc), "total_borrowings": c(total_b),
        "trade_payables_current": c(out.get("trade_payables_current")),
        "trade_payables_noncurrent": c(out.get("trade_payables_noncurrent")),
        "equity_and_liabilities": c(out.get("equity_and_liabilities")),
    }


def _best_filings(recs: list[dict], cumulative_filter: str | None) -> dict:
    """Latest revision (highest seqNumber) per (period_end, consolidated)."""
    best: dict = {}
    for r in recs:
        if cumulative_filter is not None and r.get("cumulative") != cumulative_filter:
            continue
        url = (r.get("xbrl") or "").strip()
        if not url.endswith(".xml"):
            continue
        try:
            pe = dt.datetime.strptime(r["toDate"], "%d-%b-%Y").date()
        except (KeyError, ValueError):
            continue
        consol = r.get("consolidated") == "Consolidated"
        key = (pe, consol)
        seq = int(r.get("seqNumber") or 0)
        if key not in best or seq > best[key][0]:
            best[key] = (seq, url, r.get("bank") == "Y")
    return best


def ingest_symbol(s: requests.Session, iid: str, symbol: str) -> tuple[int, int]:
    """Fetch + store quarterly P&L (+ratios) AND annual balance sheet. Returns (quarters, annuals)."""
    # ── Quarterly: full P&L + disclosed ratios ──
    q_rows = []
    for (pe, consol), (seq, url, is_bank) in _best_filings(
            list_filings(s, symbol, "Quarterly"), "Non-cumulative").items():
        try:
            fin = parse_xbrl(requests.get(url, headers=_H, timeout=30).content)
        except Exception:
            continue
        time.sleep(0.25)
        if fin.get("revenue") is None and fin.get("pat") is None:
            continue
        q_rows.append({"instrument_id": iid, "symbol": symbol, "period_end": pe,
                       "consolidated": consol, **fin, "is_bank": is_bank,
                       "seq_number": seq, "xbrl_url": url})
    nq = _db.upsert_df(f"{M}.financials_quarterly", pd.DataFrame(q_rows),
                       ["instrument_id", "period_end", "consolidated"]) if q_rows else 0

    # ── Annual: full balance sheet (Equity, Borrowings → ROE / D-E) ──
    a_rows = []
    for (pe, consol), (seq, url, _bank) in _best_filings(
            list_filings(s, symbol, "Annual"), None).items():
        try:
            bs = parse_balance_sheet(requests.get(url, headers=_H, timeout=30).content)
        except Exception:
            continue
        time.sleep(0.25)
        if bs.get("equity") is None and bs.get("total_borrowings") is None:
            continue
        a_rows.append({"instrument_id": iid, "symbol": symbol, "period_end": pe,
                       "consolidated": consol, **bs, "seq_number": seq, "xbrl_url": url})
    na = _db.upsert_df(f"{M}.financials_annual", pd.DataFrame(a_rows),
                       ["instrument_id", "period_end", "consolidated"]) if a_rows else 0
    return nq, na


def targets(only_pending: bool, limit):
    df = _db.read_df(
        f"select instrument_id, symbol from {M}.instrument_master "
        "where asset_class='stock' and kite_token is not null order by symbol")
    df["instrument_id"] = df["instrument_id"].astype(str)
    if only_pending:
        done = _db.read_df(f"select instrument_id from {M}.xbrl_state where status='done'")
        df = df[~df["instrument_id"].isin(set(done["instrument_id"].astype(str)))]
    return df.head(limit) if limit else df


def run(only_pending=True, limit=None) -> dict:
    ddl()
    tgt = targets(only_pending, limit)
    total = len(tgt); done = err = 0; qtot = atot = 0
    s = session()
    print(f"[xbrl] targets={total}", flush=True)
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, sym = r.instrument_id, r.symbol
        try:
            q, a = ingest_symbol(s, iid, sym)
            _db.upsert_df(f"{M}.xbrl_state", pd.DataFrame([{
                "instrument_id": iid, "symbol": sym, "status": "done" if (q or a) else "no_data",
                "quarters": q, "annuals": a, "error": None,
                "updated_at": dt.datetime.now(dt.UTC)}]),
                ["instrument_id"]); done += 1; qtot += q; atot += a
        except Exception as e:
            msg = repr(e)[:300]
            _db.upsert_df(f"{M}.xbrl_state", pd.DataFrame([{
                "instrument_id": iid, "symbol": sym, "status": "error",
                "quarters": None, "error": msg, "updated_at": dt.datetime.now(dt.UTC)}]),
                ["instrument_id"]); err += 1
            if any(t in msg for t in ("403", "401", "Connection", "Timeout", "JSONDecode")):
                s = session()  # refresh cookies and continue
        if n % 25 == 0 or n == total:
            print(f"[xbrl] {n}/{total} done={done} err={err} quarters={qtot} annuals={atot} last={sym}", flush=True)
        time.sleep(0.5)
    print(f"[xbrl] COMPLETE done={done} err={err} quarters={qtot} annuals={atot}", flush=True)
    return {"targets": total, "done": done, "err": err, "quarters": qtot, "annuals": atot}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    run(only_pending=not a.redo, limit=a.limit)


if __name__ == "__main__":
    main()
