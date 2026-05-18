"""D3: USDINR + DXY + India 10Y + 91d T-bill + FII flow + breadth → atlas_macro_daily."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.macro_daily import (
    BreadthComputer,
    FiiFlowFetcher,
    MacroDailyUpserter,
    UsdInrFetcher,
)


def test_usdinr_fetcher_returns_dataframe():
    yahoo_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "Close": [83.20, 83.25],
        }
    ).set_index("Date")
    with patch(
        "atlas.data_prereqs.v6.macro_daily.yf.download",
        return_value=yahoo_df,
    ):
        out = UsdInrFetcher().fetch(date(2024, 1, 1), date(2024, 1, 2))
    assert list(out.columns) == ["date", "usdinr"]
    assert out["usdinr"].iloc[0] == pytest.approx(83.20)


def test_fii_flow_fetcher_parses_nse_csv():
    """FII csv has columns: Date, Buy(₹ cr), Sell(₹ cr), Net(₹ cr)."""
    nse_csv = "Date,Buy(Cr),Sell(Cr),Net(Cr)\n01-Jan-2024,12000,11500,500\n"
    with patch("atlas.data_prereqs.v6.macro_daily.requests.get") as m:
        m.return_value.text = nse_csv
        m.return_value.status_code = 200
        out = FiiFlowFetcher().fetch(date(2024, 1, 1), date(2024, 1, 1))
    assert out["fii_cash_equity_flow_cr"].iloc[0] == 500.0


def test_breadth_computer_returns_pct_above_200dma(tmp_db_session):
    """Breadth on a given date = % of Nifty 500 stocks closing above their own 200dMA."""
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_stock_metrics_daily
            (instrument_id, date, close, ma_200)
        VALUES (gen_random_uuid(), '2024-01-02', 100, 90),
               (gen_random_uuid(), '2024-01-02', 100, 110),
               (gen_random_uuid(), '2024-01-02', 100, 95)
    """)
    )
    bc = BreadthComputer(tmp_db_session)
    breadth = bc.compute(date(2024, 1, 2))
    assert breadth == pytest.approx(66.67, abs=0.5)


def test_upserter_inserts_one_row_per_date(tmp_db_session):
    upserter = MacroDailyUpserter(tmp_db_session)
    df = pd.DataFrame(
        {
            "date": [date(2024, 1, 1)],
            "usdinr": [83.2],
            "dxy": [102.1],
            "india_10y_yield": [7.15],
            "risk_free_91d": [6.8],
            "fii_cash_equity_flow_cr": [500.0],
            "breadth_pct_above_200dma": [55.0],
        }
    )
    upserter.upsert(df)
    r = tmp_db_session.execute(
        text("SELECT * FROM atlas.atlas_macro_daily WHERE date = '2024-01-01'")
    ).first()
    assert float(r.usdinr) == 83.2
    assert float(r.breadth_pct_above_200dma) == 55.0
