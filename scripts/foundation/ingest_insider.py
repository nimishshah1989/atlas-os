#!/usr/bin/env python3
"""Ingest NSE SEBI PIT (insider trading disclosures) → foundation_staging.lens_insider.

Powers the Flow lens (insider sub-signal). Ported from jip-india.
Resumable via lens_insider_state; safe to kill/restart.

Run: python ingest_insider.py [--limit N] [--redo]
"""
from __future__ import annotations

import argparse
import datetime as dt
import time

import pandas as pd
import requests

import _db
from harness import STAGING_SCHEMA

M = STAGING_SCHEMA
_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0",
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9",
      "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading"}
_API = "https://www.nseindia.com/api/corporates-pit"

_SIGNAL = {
    "market purchase": "open_market_buy", "market sale": "open_market_sell",
    "off market": "off_market", "allotment": "preferential_allotment",
    "esos": "esop_exercise", "esop": "esop_exercise",
    "pledge": "pledge_increase", "revocation": "pledge_decrease",
    "invocation": "pledge_increase", "creeping acquisition": "creeping_acquisition",
    "acquisition": "open_market_buy", "disposal": "open_market_sell",
    "buy": "open_market_buy", "sell": "open_market_sell",
    "sale": "open_market_sell", "purchase": "open_market_buy",
}


def ddl() -> None:
    _db.exec_script(f"""
    create table if not exists {M}.lens_insider (
        instrument_id uuid not null, symbol text not null,
        transaction_date date not null, person_name text,
        person_category text, signal_type text not null,
        securities_traded numeric, value_cr numeric,
        price_per_share numeric, pledge_pct_after numeric,
        acq_mode text, source text not null default 'NSE_PIT',
        ingested_at timestamptz not null default now(),
        primary key (instrument_id, transaction_date, person_name, signal_type)
    );
    create table if not exists {M}.lens_insider_state (
        instrument_id uuid primary key, symbol text not null,
        status text not null, records integer, error text,
        updated_at timestamptz not null default now()
    );
    """)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_H)
    s.get("https://www.nseindia.com/", timeout=20)
    s.get("https://www.nseindia.com/option-chain", timeout=20)
    return s


_MIN_TXN_DATE = dt.date(2000, 1, 1)


def _parse_date(s: str) -> dt.date | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            d = dt.datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
        # Reject malformed/garbage dates (e.g. a typo'd year 2924 from the
        # multi-format source): a real PIT disclosure is never before NSE PIT
        # existed nor in the future. A 2-day grace absorbs any timezone edge.
        if _MIN_TXN_DATE <= d <= dt.date.today() + dt.timedelta(days=2):
            return d
        return None
    return None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _classify(txn_type: str, acq_mode: str) -> str:
    combined = f"{txn_type} {acq_mode}".lower()
    for kw in sorted(_SIGNAL, key=len, reverse=True):
        if kw in combined:
            return _SIGNAL[kw]
    return "other"


def ingest_symbol(s: requests.Session, iid: str, symbol: str) -> int:
    r = s.get(_API, params={"symbol": symbol, "issuer": ""}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = data.get("data", [])
    rows = []
    for rec in data:
        td = _parse_date(rec.get("acqfromDt") or rec.get("date") or "")
        if not td:
            continue
        person = (rec.get("acqName") or rec.get("personName") or "")[:500]
        if not person:
            continue
        # Real NSE PIT fields: acqMode='Market Purchase/Sale/Pledge/...' (the type),
        # tdpTransactionType='Buy/Sell', secAcq=share COUNT (not a mode), secVal=value.
        txn_type = rec.get("acqMode") or rec.get("tdpTransactionType") or ""
        acq_mode = rec.get("secType") or rec.get("derivativeType") or ""
        sig = _classify(txn_type, acq_mode)
        secs = _num(rec.get("secAcq") or rec.get("securitiesTraded"))
        value = _num(rec.get("secVal"))
        if value is not None:
            value = round(value / 1e7, 4)  # → crores
        price = _num(rec.get("befAcqSharesPer"))  # holding % before (proxy)
        pledge_after = _num(rec.get("afterAcqSharesPer"))  # holding % after
        rows.append({
            "instrument_id": iid, "symbol": symbol,
            "transaction_date": td, "person_name": person,
            "person_category": (rec.get("personCategory") or "")[:200],
            "signal_type": sig, "securities_traded": secs,
            "value_cr": value, "price_per_share": price,
            "pledge_pct_after": pledge_after, "acq_mode": acq_mode[:200],
        })
    if not rows:
        return 0
    pk = ["instrument_id", "transaction_date", "person_name", "signal_type"]
    df = pd.DataFrame(rows).drop_duplicates(subset=pk, keep="last")
    return _db.upsert_df(f"{M}.lens_insider", df, pk)


def targets(only_pending: bool, limit):
    df = _db.read_df(
        f"select instrument_id, symbol from {M}.instrument_master "
        "where asset_class='stock' and kite_token is not null order by symbol")
    df["instrument_id"] = df["instrument_id"].astype(str)
    if only_pending:
        done = _db.read_df(f"select instrument_id from {M}.lens_insider_state where status='done'")
        df = df[~df["instrument_id"].isin(set(done["instrument_id"].astype(str)))]
    return df.head(limit) if limit else df


def run(only_pending=True, limit=None) -> dict:
    ddl()
    tgt = targets(only_pending, limit)
    total = len(tgt); done = err = rtot = 0
    s = _session()
    print(f"[insider] targets={total}", flush=True)
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, sym = r.instrument_id, r.symbol
        try:
            cnt = ingest_symbol(s, iid, sym)
            _db.upsert_df(f"{M}.lens_insider_state", pd.DataFrame([{
                "instrument_id": iid, "symbol": sym,
                "status": "done" if cnt else "no_data",
                "records": cnt, "error": None,
                "updated_at": dt.datetime.now(dt.UTC)}]), ["instrument_id"])
            done += 1; rtot += cnt
        except Exception as e:
            msg = repr(e)[:300]
            _db.upsert_df(f"{M}.lens_insider_state", pd.DataFrame([{
                "instrument_id": iid, "symbol": sym, "status": "error",
                "records": None, "error": msg,
                "updated_at": dt.datetime.now(dt.UTC)}]), ["instrument_id"])
            err += 1
            if any(t in msg for t in ("403", "401", "Connection", "Timeout")):
                s = _session()
        if n % 25 == 0 or n == total:
            print(f"[insider] {n}/{total} done={done} err={err} records={rtot} last={sym}", flush=True)
        time.sleep(1.0)
    print(f"[insider] COMPLETE done={done} err={err} records={rtot}", flush=True)
    return {"targets": total, "done": done, "err": err, "records": rtot}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    run(only_pending=not a.redo, limit=a.limit)
