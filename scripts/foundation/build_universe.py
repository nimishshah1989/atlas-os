#!/usr/bin/env python3
"""Build the authoritative instrument master → atlas_foundation.instrument_master.

Universe = what we can source cleanly from Kite:
  • stocks  — NSE's official EQUITY_L.csv (symbol, name, series, ISIN, listing),
              mapped to a Kite instrument_token.
  • etfs    — Kite NSE cash instruments that look like ETFs (name/symbol markers)
              and are not in EQUITY_L.
  • indices — Kite's INDICES segment (NIFTY 50/500/BANK + sector/thematic).

instrument_id continuity: reuse the EXISTING atlas_foundation.instrument_master id
where the stock symbol matches (so existing Atlas instrument_ids keep working);
otherwise a deterministic uuid5 of the symbol. Idempotent: safe to re-run.

`--dry-run` computes the would-be active set and prints the diff vs the current
instrument_master WITHOUT writing — use it to prove the scored universe is stable
before the weekly cron mutates it.
"""

from __future__ import annotations

import argparse
import io
import re
import uuid

import _db
import ingest_kite as ik
import pandas as pd
import requests

_NS = uuid.UUID("6f9b1f6e-0000-4000-8000-a71a5000c0de")  # fixed namespace for uuid5
EQUITY_L = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
_H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}

# An instrument is an ETF if its symbol or name carries one of these markers.
_ETF_MARKERS = re.compile(
    r"(ETF|BEES|IETF|NASDAQ|HANGSENG|\bFANG\b|SENSEX|NIFTY|GOLD|SILVER|LIQUID|"
    r"BOND|GSEC|SDL|MOMENTUM|ALPHA|VALUE|QUALITY|LOWVOL|CONSUMPTION|PSUBANK|"
    r"HEALTHCARE|MIDCAP|SMALLCAP|INFRA|DIVOPP|CPSE|BHARAT22)",
    re.I,
)


def uuid_for(kind: str, symbol: str) -> str:
    return str(uuid.uuid5(_NS, f"nse:{kind}:{symbol}"))


def fetch_equity_list() -> pd.DataFrame:
    raw = requests.get(EQUITY_L, headers=_H, timeout=30).content
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame(
        {
            "symbol": df["SYMBOL"].astype(str).str.strip(),
            "name": df["NAME OF COMPANY"].astype(str).str.strip(),
            "series": df["SERIES"].astype(str).str.strip(),
            "isin": df["ISIN NUMBER"].astype(str).str.strip(),
            "listing_date": pd.to_datetime(
                df["DATE OF LISTING"], format="%d-%b-%Y", errors="coerce"
            ).dt.date,
        }
    )
    return out


def build(dry_run: bool = False) -> dict:
    eq = fetch_equity_list()
    eq_syms = set(eq["symbol"])

    kite = ik.kite_client()
    nse = kite.instruments("NSE")
    cash_tok = {
        i["tradingsymbol"]: int(i["instrument_token"]) for i in nse if i["segment"] == "NSE"
    }
    cash_name = {i["tradingsymbol"]: (i.get("name") or "") for i in nse if i["segment"] == "NSE"}
    idx = [i for i in nse if i["segment"] == "INDICES"]

    # instrument_id continuity is now self-sourced from instrument_master (the canonical
    # ids descend from the former public.de_instrument, which was dropped in the
    # single-schema consolidation). Existing ids are preserved; new symbols get a uuid5.
    de = _db.read_df(
        "select instrument_id as id, symbol from atlas_foundation.instrument_master "
        "where asset_class = 'stock'"
    )
    de_id = {str(r.symbol).strip(): str(r.id) for r in de.itertuples()}

    # Coverage universe = NIFTY 500. is_active for a stock means "in Atlas coverage",
    # NOT "tradeable on NSE". The FM-decided universe (2026-06-25) is the Nifty 500;
    # restricting is_active to it is what scopes the data-integrity gate's "every active
    # stock has a sector" / "≤21 canonical sectors" checks to the board universe instead
    # of the full ~2,375. Membership now lives in atlas_foundation (single schema).
    n500 = _db.read_df(
        "select instrument_id from atlas_foundation.de_index_constituents "
        "where index_code = 'NIFTY 500' and effective_to is null"
    )
    n500_ids = {str(x).strip() for x in n500["instrument_id"]}

    rows = []
    # stocks
    for r in eq.itertuples():
        iid = de_id.get(r.symbol) or uuid_for("stock", r.symbol)
        rows.append(
            (
                iid,
                "stock",
                r.symbol,
                r.name,
                r.isin,
                r.series,
                r.listing_date,
                cash_tok.get(r.symbol),
                "NSE",
                iid in n500_ids,
                "NSE_EQUITY_L",
            )
        )
    # etfs — cash instruments not in EQUITY_L whose symbol/name looks like an ETF.
    # Exclude indicative-NAV feed instruments (…INAV / "NAV"): not tradeable.
    for sym, tok in cash_tok.items():
        if sym in eq_syms or not re.fullmatch(r"[A-Z0-9]+", sym):
            continue
        nm = cash_name.get(sym, "")
        if "INAV" in sym.upper() or re.search(r"\bI?NAV\b", nm, re.I):
            continue
        if _ETF_MARKERS.search(sym) or _ETF_MARKERS.search(nm):
            rows.append(
                (
                    uuid_for("etf", sym),
                    "etf",
                    sym,
                    cash_name.get(sym),
                    None,
                    None,
                    None,
                    tok,
                    "NSE",
                    True,
                    "KITE_NSE_ETF",
                )
            )
    # indices
    for i in idx:
        sym = i["tradingsymbol"]
        rows.append(
            (
                uuid_for("index", sym),
                "index",
                sym,
                i.get("name"),
                None,
                None,
                None,
                int(i["instrument_token"]),
                "NSE",
                True,
                "KITE_INDICES",
            )
        )

    cols = [
        "instrument_id",
        "asset_class",
        "symbol",
        "name",
        "isin",
        "series",
        "listing_date",
        "kite_token",
        "exchange",
        "is_active",
        "source",
    ]
    df = pd.DataFrame(rows, columns=cols).drop_duplicates("instrument_id")

    # Before/after guardrail: prove the scored universe (active stocks) is stable before
    # the write. Membership can legitimately drift on an NSE NIFTY-500 reconstitution;
    # the diff surfaces exactly which symbols flip so a change is never silent.
    cur_active = set(
        _db.read_df(
            "select instrument_id::text id from atlas_foundation.instrument_master "
            "where asset_class = 'stock' and is_active"
        )["id"]
    )
    new_active = set(df.loc[(df["asset_class"] == "stock") & (df["is_active"]), "instrument_id"])
    added, removed = new_active - cur_active, cur_active - new_active
    print(
        f"  active stocks: {len(cur_active)} -> {len(new_active)} (+{len(added)} / -{len(removed)})"
    )
    if added or removed:
        sym = {str(r.instrument_id): r.symbol for r in df.itertuples()}
        if added:
            print("    ADDED:  ", ", ".join(sorted(sym.get(i, i) for i in added)))
        if removed:
            rem = _db.read_df(
                "select instrument_id::text id, symbol from atlas_foundation.instrument_master "
                "where instrument_id = any(%(ids)s)",
                {"ids": list(removed)},
            )
            print("    REMOVED:", ", ".join(sorted(rem["symbol"])))

    if dry_run:
        print("  DRY RUN — no write.")
        by = df.groupby("asset_class").size().to_dict()
        return {"written": 0, "dry_run": True, "would_write": len(df), "by_class": by}

    df["updated_at"] = pd.Timestamp.now(tz="Asia/Kolkata")  # stamp the refresh (G6 freshness)
    n = _db.upsert_df("atlas_foundation.instrument_master", df, ["instrument_id"])

    counts = (
        df.groupby("asset_class")
        .agg(total=("symbol", "size"), on_kite=("kite_token", lambda s: int(s.notna().sum())))
        .to_dict("index")
    )
    return {"written": n, "by_class": counts}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute + diff the universe, no write")
    args = ap.parse_args()
    print(build(dry_run=args.dry_run))
