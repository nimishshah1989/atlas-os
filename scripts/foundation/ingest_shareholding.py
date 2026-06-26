#!/usr/bin/env python3
"""Ingest NSE quarterly shareholding patterns → foundation_staging.lens_shareholding.

Powers the Flow lens (institutional ownership sub-signal). Ported from jip-india.
The NSE corporate-share-holdings-master API returns a flat list of quarterly
records with aggregate promoter/public percentages. For detailed FII/DII/MF
breakdowns the XBRL attachment would need parsing (deferred — levels are enough
for v1).

Resumable via lens_shareholding_state; safe to kill/restart.

Run: python ingest_shareholding.py [--limit N] [--redo]
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
      "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"}
_API = "https://www.nseindia.com/api/corporate-share-holdings-master"


def ddl() -> None:
    _db.exec_script(f"""
    create table if not exists {M}.lens_shareholding (
        instrument_id uuid not null, symbol text not null,
        period_end date not null,
        promoter_pct numeric, public_pct numeric,
        employee_trusts_pct numeric,
        source text not null default 'NSE',
        ingested_at timestamptz not null default now(),
        primary key (instrument_id, period_end)
    );
    create table if not exists {M}.lens_shareholding_state (
        instrument_id uuid primary key, symbol text not null,
        status text not null, quarters integer, error text,
        updated_at timestamptz not null default now()
    );
    """)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_H)
    s.get("https://www.nseindia.com/", timeout=20)
    s.get("https://www.nseindia.com/option-chain", timeout=20)
    return s


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_date(s: str) -> dt.date | None:
    for fmt in ("%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def ingest_symbol(s: requests.Session, iid: str, symbol: str) -> int:
    r = s.get(_API, params={"index": "equities", "symbol": symbol}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        data = [data] if isinstance(data, dict) else []
    rows = []
    for rec in data:
        date_str = rec.get("date") or ""
        pe = _parse_date(date_str)
        if not pe:
            continue
        prom = _num(rec.get("pr_and_prgrp"))
        pub = _num(rec.get("public_val"))
        emp = _num(rec.get("employeeTrusts"))
        rows.append({
            "instrument_id": iid, "symbol": symbol, "period_end": pe,
            "promoter_pct": prom, "public_pct": pub,
            "employee_trusts_pct": emp,
        })
    if not rows:
        return 0
    pk = ["instrument_id", "period_end"]
    df = pd.DataFrame(rows).drop_duplicates(subset=pk, keep="last")
    return _db.upsert_df(f"{M}.lens_shareholding", df, pk)


def targets(only_pending: bool, limit):
    df = _db.read_df(
        f"select instrument_id, symbol from {M}.instrument_master "
        "where asset_class='stock' and kite_token is not null order by symbol")
    df["instrument_id"] = df["instrument_id"].astype(str)
    if only_pending:
        done = _db.read_df(f"select instrument_id from {M}.lens_shareholding_state where status='done'")
        df = df[~df["instrument_id"].isin(set(done["instrument_id"].astype(str)))]
    return df.head(limit) if limit else df


def run(only_pending=True, limit=None) -> dict:
    ddl()
    tgt = targets(only_pending, limit)
    total = len(tgt); done = err = qtot = 0
    s = _session()
    print(f"[shareholding] targets={total}", flush=True)
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, sym = r.instrument_id, r.symbol
        try:
            cnt = ingest_symbol(s, iid, sym)
            _db.upsert_df(f"{M}.lens_shareholding_state", pd.DataFrame([{
                "instrument_id": iid, "symbol": sym,
                "status": "done" if cnt else "no_data",
                "quarters": cnt, "error": None,
                "updated_at": dt.datetime.now(dt.UTC)}]), ["instrument_id"])
            done += 1; qtot += cnt
        except Exception as e:
            msg = repr(e)[:300]
            _db.upsert_df(f"{M}.lens_shareholding_state", pd.DataFrame([{
                "instrument_id": iid, "symbol": sym, "status": "error",
                "quarters": None, "error": msg,
                "updated_at": dt.datetime.now(dt.UTC)}]), ["instrument_id"])
            err += 1
            if any(t in msg for t in ("403", "401", "Connection", "Timeout")):
                s = _session()
        if n % 25 == 0 or n == total:
            print(f"[shareholding] {n}/{total} done={done} err={err} qtrs={qtot} last={sym}", flush=True)
        time.sleep(1.0)
    print(f"[shareholding] COMPLETE done={done} err={err} qtrs={qtot}", flush=True)
    return {"targets": total, "done": done, "err": err, "quarters": qtot}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    run(only_pending=not a.redo, limit=a.limit)
