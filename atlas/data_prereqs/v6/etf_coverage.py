"""D2: ETF coverage check + Yahoo backfill for crisis-sleeve ETFs.

Verifies that GOLDBEES and the G-Sec proxy ETF have at least target_years
of daily history in atlas_etf_metrics_daily. Where coverage is short,
Yahoo Finance fills the gap.

Yahoo symbol mapping is intentionally explicit: NSE ETFs are .NS suffixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import structlog
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

SLEEVE_ETFS: tuple[str, ...] = ("GOLDBEES", "LIQUIDBEES", "BHARAT22 ETF")
YAHOO_MAP: dict[str, str] = {
    "GOLDBEES": "GOLDBEES.NS",
    "LIQUIDBEES": "LIQUIDBEES.NS",
    "BHARAT22 ETF": "BHARAT22.NS",
}


@dataclass(frozen=True)
class Coverage:
    symbol: str
    first_date: date | None
    last_date: date | None
    gap_days_to_target: int


@dataclass
class EtfCoverageChecker:
    session: Session
    target_years: int = 10

    def coverage_for(self, symbol: str, reference_date: date) -> Coverage:
        row = self.session.execute(
            text("""
            SELECT MIN(e.date) AS first_date, MAX(e.date) AS last_date
              FROM atlas.atlas_etf_metrics_daily e
              JOIN atlas.atlas_instrument_master i USING (instrument_id)
             WHERE i.symbol = :s
        """),
            {"s": symbol},
        ).first()
        if row is None or row.first_date is None:
            return Coverage(symbol, None, None, self.target_years * 365)
        target_first = reference_date.toordinal() - (self.target_years * 365)
        actual_first = row.first_date.toordinal()
        gap = max(0, actual_first - target_first)
        return Coverage(symbol, row.first_date, row.last_date, gap)


@dataclass
class YahooBackfiller:
    session: Session

    def _resolve_iid(self, symbol: str) -> str:
        row = self.session.execute(
            text("SELECT instrument_id FROM atlas.atlas_instrument_master " "WHERE symbol = :s"),
            {"s": symbol},
        ).first()
        if row is None:
            raise LookupError(symbol)
        return str(row.instrument_id)

    def backfill(
        self,
        atlas_symbol: str,
        yahoo_symbol: str,
        start: date,
        end: date,
    ) -> int:
        df = yf.download(
            yahoo_symbol,
            start=start,
            end=end + pd.Timedelta(days=1),
            progress=False,
        )
        if df.empty:
            log.warning("yahoo_no_data", symbol=yahoo_symbol)
            return 0
        iid = self._resolve_iid(atlas_symbol)
        # Handle MultiIndex columns returned by newer yfinance versions
        if isinstance(df.columns, pd.MultiIndex):
            close_col = df.xs("Close", axis=1, level=0)
            close_series = close_col.iloc[:, 0] if hasattr(close_col, "iloc") else close_col
        else:
            close_series = df["Close"]
        rows = [
            {"iid": iid, "date": idx.date(), "close": float(close_series.loc[idx])}
            for idx in df.index
        ]
        self.session.execute(
            text("""
            INSERT INTO atlas.atlas_etf_metrics_daily (instrument_id, date, close)
            VALUES (:iid, :date, :close)
            ON CONFLICT (instrument_id, date) DO NOTHING
        """),
            rows,
        )
        self.session.commit()
        log.info("yahoo_backfill", symbol=atlas_symbol, rows=len(rows))
        return len(rows)
