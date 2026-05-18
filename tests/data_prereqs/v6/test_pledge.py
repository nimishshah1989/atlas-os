"""D5: Promoter pledge quarterly ingest + forward-fill into atlas_governance_daily."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from atlas.data_prereqs.v6.pledge import (
    PledgeQuarterIngester,
    compute_pledge_ratio,
    parse_pledge_filing,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pledge_sample.json"


def test_compute_pledge_ratio_normal():
    assert compute_pledge_ratio(1000000, 600000) == pytest.approx(60.0)


def test_compute_pledge_ratio_zero_total_returns_none():
    assert compute_pledge_ratio(0, 0) is None


def test_parse_pledge_filing_yields_per_symbol_rows():
    payload = json.loads(FIXTURE.read_text())
    rows = parse_pledge_filing(payload)
    assert len(rows) == 2
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["DHFL"]["pledge_ratio_pct"] == pytest.approx(60.0)
    assert by_symbol["TCS"]["pledge_ratio_pct"] == pytest.approx(0.0)
    assert by_symbol["DHFL"]["effective_date"] == date(2024, 9, 30)


def test_ingester_forward_fills_to_next_quarter_minus_1_day(tmp_db_session):
    """If we ingest Q3 2024 (2024-09-30), rows should be created daily for
    2024-09-30 through next quarter end - 1 (2024-12-30)."""
    iid = uuid.uuid4()
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'DHFL') ON CONFLICT DO NOTHING
    """),
        {"i": str(iid)},
    )
    ing = PledgeQuarterIngester(tmp_db_session)
    ing.ingest_filing(json.loads(FIXTURE.read_text()))
    rows = tmp_db_session.execute(
        text("""
        SELECT COUNT(*) AS n FROM atlas.atlas_governance_daily
         WHERE instrument_id = :i
           AND pledge_ratio_pct = 60.00
    """),
        {"i": str(iid)},
    ).first()
    # 2024-09-30 through 2024-12-30 inclusive = 92 days
    assert rows.n == 92
