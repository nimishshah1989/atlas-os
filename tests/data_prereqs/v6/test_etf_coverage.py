"""D2: ETF coverage check + Yahoo backfill for crisis-sleeve ETFs."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch

import pandas as pd
from sqlalchemy import text

from atlas.data_prereqs.v6.etf_coverage import (
    SLEEVE_ETFS,
    EtfCoverageChecker,
    YahooBackfiller,
)


def test_sleeve_etfs_list_has_required_symbols():
    assert "GOLDBEES" in SLEEVE_ETFS
    assert any(s.startswith("LIQUIDBEES") or "BHARAT" in s for s in SLEEVE_ETFS)


def test_coverage_check_reports_gap(tmp_db_session):
    """coverage_for returns (first_date, last_date, gap_days_to_target)."""
    iid = uuid.uuid4()
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'GOLDBEES')
        ON CONFLICT DO NOTHING
    """),
        {"i": str(iid)},
    )
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_etf_metrics_daily (instrument_id, date, close)
        VALUES (:i, '2020-01-01', 100.0), (:i, '2020-01-02', 101.0)
    """),
        {"i": str(iid)},
    )
    chk = EtfCoverageChecker(tmp_db_session, target_years=10)
    cov = chk.coverage_for("GOLDBEES", reference_date=date(2025, 1, 1))
    assert cov.first_date == date(2020, 1, 1)
    assert cov.last_date == date(2020, 1, 2)
    assert cov.gap_days_to_target > 1800  # ~5y short


def test_yahoo_backfiller_inserts_missing_rows(tmp_db_session):
    """Backfiller fetches Yahoo and inserts rows not already in DB."""
    iid = uuid.uuid4()
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'GOLDBEES')
        ON CONFLICT DO NOTHING
    """),
        {"i": str(iid)},
    )
    yahoo_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2014-01-01", "2014-01-02"]),
            "Close": [42.5, 42.7],
        }
    )
    with patch(
        "atlas.data_prereqs.v6.etf_coverage.yf.download",
        return_value=yahoo_df.set_index("Date"),
    ):
        bf = YahooBackfiller(tmp_db_session)
        n = bf.backfill(
            "GOLDBEES",
            "GOLDBEES.NS",
            start=date(2014, 1, 1),
            end=date(2014, 1, 2),
        )
    assert n == 2
    rows = tmp_db_session.execute(
        text("SELECT COUNT(*) AS n FROM atlas.atlas_etf_metrics_daily " "WHERE instrument_id = :i"),
        {"i": str(iid)},
    ).first()
    assert rows.n == 2
