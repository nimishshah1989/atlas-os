"""Instrument rows for the index-membership tests, built from the REAL directory files.

Nothing here is typed in: the name, exchange and ETF flag come from the 2026-09-04 Nasdaq
Trader files and the CIK from the SEC file under ``tests/fixtures/global/symbology``; the
``instrument_id`` is minted by P1-A's own rule (``atlas.global_market.identity``:
``uuid5(NAMESPACE_URL, "us:{class}:{cik}:{symbol}")``). This is test scaffolding only —
``build_identity.py`` is the one script that mints identities.

The directories carry no listing date, so these rows have unbounded listing windows — the
delisted-holder branch of the spell resolver needs P1-A's survivorship rows (Stooq archive)
and is not exercised here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atlas.global_market import identity
from atlas.global_market.providers.symbology import (
    parse_nasdaq_symbol_directory,
    parse_sec_company_tickers,
)

SYMBOLOGY = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "global" / "symbology"
# SPY (the anchor ETF, not an index member) + six current S&P 500 members present in the
# 2026-09-04 directories: three fja05680 knows (AAPL, NVDA, MSFT) and the three SSGA lists
# that joined after fja05680's last row (RDDT, FERG, VMRK).
SYMBOLS: tuple[str, ...] = ("SPY", "AAPL", "NVDA", "MSFT", "RDDT", "FERG", "VMRK")


@dataclass(frozen=True, slots=True)
class ScaffoldRow:
    instrument_id: str
    asset_class: str
    symbol: str
    name: str
    exchange: str
    cik: str


def scaffold_rows(symbols: tuple[str, ...] = SYMBOLS) -> list[ScaffoldRow]:
    nasdaq = parse_nasdaq_symbol_directory((SYMBOLOGY / "nasdaqlisted.txt").read_text())
    other = parse_nasdaq_symbol_directory((SYMBOLOGY / "otherlisted.txt").read_text())
    sec = parse_sec_company_tickers((SYMBOLOGY / "company_tickers.json").read_text())
    rows: list[ScaffoldRow] = []
    for symbol in symbols:
        n = nasdaq.loc[nasdaq["symbol"] == symbol]
        o = other.loc[other["act_symbol"] == symbol]
        if len(n) == 1:
            name, is_etf, exchange = str(n["security_name"].item()), bool(n["etf"].item()), "NASDAQ"
        elif len(o) == 1:
            name, is_etf = str(o["security_name"].item()), bool(o["etf"].item())
            exchange = identity.exchange_name(str(o["exchange"].item()), symbol)
        else:
            raise LookupError(f"{symbol}: not exactly one directory row")
        cik = sec.loc[sec["ticker"] == symbol, "cik"]
        if len(cik) != 1:
            raise LookupError(f"{symbol}: not exactly one SEC row")
        asset_class = "etf" if is_etf else "stock"
        key = identity.instrument_key(asset_class, str(cik.item()), symbol, None)
        rows.append(
            ScaffoldRow(
                str(identity.mint(key)), asset_class, symbol, name, exchange, str(cik.item())
            )
        )
    return rows
