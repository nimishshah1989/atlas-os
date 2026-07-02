#!/usr/bin/env python3
"""Ingest NSE bulk/block deals → atlas_foundation.lens_bulk_deals.

Powers the Flow lens (smart-money sub-signal). Ported from jip-india.
Unlike the per-symbol fetchers, the deals endpoint returns ALL recent deals
in one call — so this is a single-shot fetch, not a per-symbol loop.

Run: python ingest_bulk_deals.py
"""

from __future__ import annotations

import datetime as dt

import _db
import pandas as pd
import requests
from harness import STAGING_SCHEMA

M = STAGING_SCHEMA
_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/large-deals",
}
_API = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"

# Institutional keywords for detection
_INST_KW = [
    "mutual fund",
    "insurance",
    "pension",
    "provident",
    "bank of",
    "fii",
    "dii",
    "securities",
    "capital",
    "asset management",
    "investment",
    "trustee",
    "custody",
    "clearing",
    "depository",
]

# Superstar investors (curated, partial — extend as needed)
_SUPERSTARS = {
    "kacholia": "Ashish Kacholia",
    "kedia": "Vijay Kedia",
    "damani": "Radhakishan Damani",
    "jhunjhunwala": "Jhunjhunwala Legacy",
    "rekha jhunjhunwala": "Jhunjhunwala Legacy",
    "dolly khanna": "Dolly Khanna",
    "porinju": "Porinju Veliyath",
    "sunil singhania": "Sunil Singhania",
    "anil kumar goel": "Anil Kumar Goel",
    "mukul agrawal": "Mukul Agrawal",
}


def ddl() -> None:
    _db.exec_script(f"""
    create table if not exists {M}.lens_bulk_deals (
        instrument_id uuid, symbol text not null,
        deal_date date not null, deal_type text not null,
        client_name text not null,
        buy_sell text not null, qty bigint, price numeric,
        is_institutional boolean, is_superstar boolean,
        superstar_name text,
        source text not null default 'NSE',
        ingested_at timestamptz not null default now(),
        primary key (symbol, deal_date, client_name, buy_sell)
    );
    """)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_H)
    s.get("https://www.nseindia.com/", timeout=20)
    s.get("https://www.nseindia.com/option-chain", timeout=20)
    return s


def _parse_date(s: str) -> dt.date | None:
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _is_institutional(name: str) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in _INST_KW)


def _match_superstar(name: str) -> str | None:
    nl = name.lower()
    for kw, canonical in _SUPERSTARS.items():
        if kw in nl:
            return canonical
    return None


def run() -> dict:
    ddl()
    # Build symbol → instrument_id mapping
    im = _db.read_df(
        f"select instrument_id, symbol from {M}.instrument_master "
        "where asset_class='stock' and kite_token is not null"
    )
    sym_to_iid = dict(zip(im["symbol"], im["instrument_id"].astype(str), strict=False))

    s = _session()
    r = s.get(_API, timeout=30)
    r.raise_for_status()
    data = r.json()

    rows = []
    for deal_type, key in [("BULK", "BULK_DEALS_DATA"), ("BLOCK", "BLOCK_DEALS_DATA")]:
        deals = data.get(key, [])
        for d in deals:
            sym = (d.get("symbol") or d.get("tkr") or "").strip()
            if not sym:
                continue
            dd = _parse_date(d.get("date") or d.get("dealDate") or "")
            if not dd:
                continue
            client = (d.get("clientName") or d.get("client") or "")[:500]
            bs = (d.get("buySell") or d.get("buyOrSell") or "").strip().upper()
            if bs not in ("BUY", "SELL"):
                bs = "BUY" if "buy" in (d.get("buySell") or "").lower() else "SELL"
            qty = _num(d.get("qty") or d.get("quantity"))
            price = _num(d.get("wAvgPrice") or d.get("avgPrice") or d.get("price"))
            iid = sym_to_iid.get(sym)
            ss_name = _match_superstar(client)
            rows.append(
                {
                    "instrument_id": iid,
                    "symbol": sym,
                    "deal_date": dd,
                    "deal_type": deal_type,
                    "client_name": client,
                    "buy_sell": bs,
                    "qty": int(qty) if qty else None,
                    "price": round(price, 2) if price else None,
                    "is_institutional": _is_institutional(client),
                    "is_superstar": ss_name is not None,
                    "superstar_name": ss_name,
                }
            )

    if not rows:
        print("[bulk_deals] no deals found", flush=True)
        return {"deals": 0}

    pk = ["symbol", "deal_date", "client_name", "buy_sell"]
    df = pd.DataFrame(rows).drop_duplicates(subset=pk, keep="last")
    n = _db.upsert_df(f"{M}.lens_bulk_deals", df, pk)
    print(
        f"[bulk_deals] upserted {n} deals "
        f"(bulk={sum(1 for r in rows if r['deal_type'] == 'BULK')}, "
        f"block={sum(1 for r in rows if r['deal_type'] == 'BLOCK')}, "
        f"superstars={sum(1 for r in rows if r['is_superstar'])})",
        flush=True,
    )
    return {"deals": n}


if __name__ == "__main__":
    run()
