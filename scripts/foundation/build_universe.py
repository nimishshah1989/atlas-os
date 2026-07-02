#!/usr/bin/env python3
"""Build the authoritative instrument master → atlas_foundation.instrument_master.

Universe = what we can source cleanly from Kite:
  • stocks  — NSE's official EQUITY_L.csv (symbol, name, series, ISIN, listing),
              mapped to a Kite instrument_token.
  • etfs    — Kite NSE cash instruments that look like ETFs (name/symbol markers)
              and are not in EQUITY_L.
  • indices — Kite's INDICES segment (NIFTY 50/500/BANK + sector/thematic).

instrument_id continuity: reuse public.de_instrument.id where the stock symbol
matches (so existing Atlas instrument_ids keep working); otherwise a deterministic
uuid5 of the symbol. Idempotent: safe to re-run.
"""

from __future__ import annotations

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


def build() -> dict:
    eq = fetch_equity_list()
    eq_syms = set(eq["symbol"])

    kite = ik.kite_client()
    nse = kite.instruments("NSE")
    cash_tok = {
        i["tradingsymbol"]: int(i["instrument_token"]) for i in nse if i["segment"] == "NSE"
    }
    cash_name = {i["tradingsymbol"]: (i.get("name") or "") for i in nse if i["segment"] == "NSE"}
    idx = [i for i in nse if i["segment"] == "INDICES"]

    de = _db.read_df("select id, symbol from public.de_instrument")
    de_id = {str(r.symbol).strip(): str(r.id) for r in de.itertuples()}

    # Coverage universe = NIFTY 500. is_active for a stock means "in Atlas coverage",
    # NOT "tradeable on NSE" (tradeability is preserved in public.de_instrument). The
    # FM-decided universe (2026-06-25) is the Nifty 500; restricting is_active to it is
    # what scopes the data-integrity gate's "every active stock has a sector" /
    # "≤21 canonical sectors" checks to the board universe instead of the full ~2,375.
    n500 = _db.read_df(
        "select instrument_id from public.de_index_constituents "
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
    n = _db.upsert_df("atlas_foundation.instrument_master", df, ["instrument_id"])

    counts = (
        df.groupby("asset_class")
        .agg(total=("symbol", "size"), on_kite=("kite_token", lambda s: int(s.notna().sum())))
        .to_dict("index")
    )
    return {"written": n, "by_class": counts}


if __name__ == "__main__":
    print(build())
