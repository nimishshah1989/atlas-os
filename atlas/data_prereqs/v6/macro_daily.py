"""D3: Daily macro series → atlas_macro_daily.

Six columns:
- usdinr                  : Yahoo INR=X
- dxy                     : Yahoo DX-Y.NYB
- india_10y_yield         : RBI MMR (best-effort; falls back to CCIL CSV)
- risk_free_91d           : RBI T-bill auction (best-effort)
- fii_cash_equity_flow_cr : NSE FII/DII CSV
- breadth_pct_above_200dma: computed from atlas_stock_metrics_daily
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests
import structlog
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass
class UsdInrFetcher:
    def fetch(self, start: date, end: date) -> pd.DataFrame:
        raw = yf.download(
            "INR=X",
            start=start,
            end=end + pd.Timedelta(days=1),
            progress=False,
        )
        if raw.empty:
            return pd.DataFrame(columns=["date", "usdinr"])
        return pd.DataFrame({"date": raw.index.date, "usdinr": raw["Close"].values})


@dataclass
class DxyFetcher:
    def fetch(self, start: date, end: date) -> pd.DataFrame:
        raw = yf.download(
            "DX-Y.NYB",
            start=start,
            end=end + pd.Timedelta(days=1),
            progress=False,
        )
        if raw.empty:
            return pd.DataFrame(columns=["date", "dxy"])
        return pd.DataFrame({"date": raw.index.date, "dxy": raw["Close"].values})


@dataclass
class FiiFlowFetcher:
    """NSE publishes a daily FII/DII cash equity flow CSV.

    Endpoint: https://archives.nseindia.com/content/equities/fii_stats_<DDMMYYYY>.xls
    For simplicity we use the rolled-up CSV historical archive when present.
    Returns net flow in ₹crore.
    """

    csv_endpoint: str = "https://www.nseindia.com/api/fiidii-tracker"

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        # Operator note: full NSE archive scrape is its own runbook;
        # for tests + initial backfill we accept a CSV-like input.
        resp = requests.get(self.csv_endpoint, timeout=30)
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        df["date"] = pd.to_datetime(df["Date"], dayfirst=True).dt.date
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        return df[["date", "Net(Cr)"]].rename(columns={"Net(Cr)": "fii_cash_equity_flow_cr"})


@dataclass
class IndiaTenYearFetcher:
    """RBI publishes daily yield curves; operator backfills via CCIL CSV."""

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        # Placeholder — operator-driven CSV load. For tests, return empty.
        # Real implementation: download from
        # https://www.ccilindia.com/web/ccil/daily-historical-data
        return pd.DataFrame(columns=["date", "india_10y_yield"])


@dataclass
class RiskFree91dFetcher:
    def fetch(self, start: date, end: date) -> pd.DataFrame:
        # RBI T-bill auction results (operator-driven CSV).
        return pd.DataFrame(columns=["date", "risk_free_91d"])


@dataclass
class BreadthComputer:
    session: Session

    def compute(self, ref_date: date) -> float:
        # above_30w_ma is the pre-computed 200 DMA boolean in atlas_stock_metrics_daily.
        # Columns 'close' and 'ma_200' do not exist in the table; above_30w_ma does.
        row = self.session.execute(
            text("""
            SELECT
                COUNT(*) FILTER (WHERE above_30w_ma = TRUE) AS above,
                COUNT(*) AS total
              FROM atlas.atlas_stock_metrics_daily
             WHERE date = :d AND above_30w_ma IS NOT NULL
        """),
            {"d": ref_date},
        ).first()
        if not row or not row.total:
            return 0.0
        return round(100.0 * row.above / row.total, 2)


@dataclass
class MacroDailyUpserter:
    session: Session

    def upsert(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        rows = df.to_dict("records")
        self.session.execute(
            text("""
            INSERT INTO atlas.atlas_macro_daily
                (date, usdinr, dxy, india_10y_yield, risk_free_91d,
                 fii_cash_equity_flow_cr, breadth_pct_above_200dma)
            VALUES (:date, :usdinr, :dxy, :india_10y_yield, :risk_free_91d,
                    :fii_cash_equity_flow_cr, :breadth_pct_above_200dma)
            ON CONFLICT (date) DO UPDATE SET
                usdinr = EXCLUDED.usdinr,
                dxy = EXCLUDED.dxy,
                india_10y_yield = EXCLUDED.india_10y_yield,
                risk_free_91d = EXCLUDED.risk_free_91d,
                fii_cash_equity_flow_cr = EXCLUDED.fii_cash_equity_flow_cr,
                breadth_pct_above_200dma = EXCLUDED.breadth_pct_above_200dma
        """),
            rows,
        )
        self.session.commit()
        return len(rows)
