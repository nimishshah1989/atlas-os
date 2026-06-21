#!/usr/bin/env python3
"""Ingest ONE day of NSE Bhavcopy → staging (idempotent).

Source of truth (docs/atlas-data-foundation.md §2): NSE's official EOD archives,
reachable as static files from archives.nseindia.com (the bot-block only affects
the www.nseindia.com/api/* JSON endpoints):

  • UDiFF Common Bhavcopy (CM segment)  — stocks + ETFs (ETFs are series EQ here)
      content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip
  • Indices close-all                    — all index OHLC for the day
      content/indices/ind_close_all_<DDMMYYYY>.csv

Stocks are matched to public.de_instrument by ISIN (then symbol) to obtain the
instrument_id. ETFs are matched against the existing de_etf_ohlcv ticker set.
Writes raw OHLCV into foundation_staging; adjustment + technicals run separately.

Cost rule: pure-Python download/parse; emits only small counts.
"""

from __future__ import annotations

import argparse
import io
import zipfile
from datetime import date, datetime

import pandas as pd
import requests

import _db

NSE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/csv,application/zip,*/*",
    "Referer": "https://www.nseindia.com/",
}
_ARCHIVES = "https://archives.nseindia.com"


def cm_url(d: date) -> str:
    return f"{_ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"


def index_url(d: date) -> str:
    return f"{_ARCHIVES}/content/indices/ind_close_all_{d:%d%m%Y}.csv"


def _get(url: str, timeout: int = 60) -> bytes:
    r = requests.get(url, headers=NSE_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content


# ── Download + parse ────────────────────────────────────────────────────────
def download_cm(d: date) -> pd.DataFrame:
    """Raw UDiFF CM bhavcopy as a DataFrame."""
    blob = _get(cm_url(d))
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        return pd.read_csv(io.BytesIO(zf.read(name)))


def download_indices(d: date) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(_get(index_url(d))))


def parse_cm(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalise UDiFF rows to canonical OHLCV columns (one row per instrument)."""
    df = raw.rename(columns={
        "TckrSymb": "symbol", "ISIN": "isin", "SctySrs": "series",
        "OpnPric": "open", "HghPric": "high", "LwPric": "low", "ClsPric": "close",
        "PrvsClsgPric": "prev_close", "TtlTradgVol": "volume",
        "TtlNbOfTxsExctd": "trades", "TradDt": "date",
    })
    keep = ["symbol", "isin", "series", "date", "open", "high", "low", "close",
            "prev_close", "volume", "trades"]
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for c in ("open", "high", "low", "close", "prev_close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("volume", "trades"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["isin"] = df["isin"].astype(str).str.strip()
    return df


def parse_indices(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={
        "Index Name": "index_code", "Index Date": "date",
        "Open Index Value": "open", "High Index Value": "high",
        "Low Index Value": "low", "Closing Index Value": "close", "Volume": "volume",
    })[["index_code", "date", "open", "high", "low", "close", "volume"]].copy()
    df["index_code"] = df["index_code"].astype(str).str.strip().str.upper()  # match de_index_prices
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y").dt.date
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
    return df


# ── Universe mapping ─────────────────────────────────────────────────────────
def instrument_map() -> pd.DataFrame:
    """de_instrument rows for matching bhavcopy symbols → instrument_id."""
    return _db.read_df(
        "select id as instrument_id, symbol, isin, nifty_500, is_active "
        "from public.de_instrument")


def etf_tickers() -> set[str]:
    df = _db.read_df("select distinct ticker from public.de_etf_ohlcv")
    return set(df["ticker"].astype(str).str.strip())


# ── Write to staging ─────────────────────────────────────────────────────────
def write_stocks(parsed: pd.DataFrame, imap: pd.DataFrame, source: str,
                 only_symbols: list[str] | None = None) -> int:
    """Map equity rows to instrument_id and upsert into ohlcv_stock (adj=raw at ingest)."""
    eq = parsed[parsed["series"].isin(["EQ", "BE", "BZ"])].copy()
    if only_symbols:
        eq = eq[eq["symbol"].isin(only_symbols)]
    # match by ISIN first, then symbol
    by_isin = imap.dropna(subset=["isin"]).set_index("isin")["instrument_id"].to_dict()
    by_sym = imap.set_index("symbol")["instrument_id"].to_dict()
    eq["instrument_id"] = eq["isin"].map(by_isin)
    miss = eq["instrument_id"].isna()
    eq.loc[miss, "instrument_id"] = eq.loc[miss, "symbol"].map(by_sym)
    eq = eq.dropna(subset=["instrument_id"])
    out = pd.DataFrame({
        "instrument_id": eq["instrument_id"].astype(str),
        "symbol": eq["symbol"], "date": eq["date"],
        "open": eq["open"], "high": eq["high"], "low": eq["low"], "close": eq["close"],
        "prev_close": eq["prev_close"],
        # at ingest, adjusted = raw (factor 1); back-adjustment runs in adjust step
        "open_adj": eq["open"], "high_adj": eq["high"], "low_adj": eq["low"],
        "close_adj": eq["close"], "adj_factor": 1.0,
        "volume": eq["volume"], "trades": eq["trades"], "series": eq["series"],
        "source": source,
    })
    return _db.upsert_df("foundation_staging.ohlcv_stock", out, ["instrument_id", "date"])


def write_indices(parsed: pd.DataFrame, source: str) -> int:
    out = parsed.assign(source=source)
    return _db.upsert_df("foundation_staging.index_prices", out, ["index_code", "date"])


def ingest_day(d: date, only_symbols: list[str] | None = None) -> dict:
    raw_cm = download_cm(d)
    raw_idx = download_indices(d)
    stocks = parse_cm(raw_cm)
    indices = parse_indices(raw_idx)
    imap = instrument_map()
    n_stock = write_stocks(stocks, imap, source="NSE_UDIFF_CM", only_symbols=only_symbols)
    n_index = write_indices(indices, source="NSE_IND_CLOSE_ALL")
    return {"date": str(d), "cm_rows": len(stocks), "index_rows": len(indices),
            "stocks_written": n_stock, "indices_written": n_index}


def main():
    ap = argparse.ArgumentParser(description="Ingest one day of NSE Bhavcopy → staging")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD trading day")
    ap.add_argument("--symbols", nargs="*", help="restrict stock write to these symbols")
    args = ap.parse_args()
    d = datetime.strptime(args.date, "%Y-%m-%d").date()
    res = ingest_day(d, only_symbols=args.symbols)
    print(res)


if __name__ == "__main__":
    main()
