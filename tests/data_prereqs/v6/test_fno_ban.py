"""D4: F&O ban list daily fetch + upsert into atlas_governance_daily."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

from atlas.data_prereqs.v6.fno_ban import FnoBanFetcher, FnoBanUpserter

FIXTURE = Path(__file__).parent / "fixtures" / "fno_ban_sample.csv"


def test_fetcher_parses_csv():
    with patch("atlas.data_prereqs.v6.fno_ban.requests.get") as m:
        m.return_value.text = FIXTURE.read_text()
        m.return_value.status_code = 200
        symbols = FnoBanFetcher().fetch_for_date(date(2024, 6, 1))
    assert symbols == {"IDEA", "RBLBANK", "DELTACORP"}


def test_upserter_sets_in_fno_ban_flag(tmp_db_session):
    riid = uuid.uuid4()
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'IDEA') ON CONFLICT DO NOTHING
    """),
        {"i": str(riid)},
    )
    upserter = FnoBanUpserter(tmp_db_session)
    upserter.upsert(date(2024, 6, 1), {"IDEA"})
    row = tmp_db_session.execute(
        text("""
        SELECT in_fno_ban_list FROM atlas.atlas_governance_daily
        WHERE instrument_id = :i AND date = '2024-06-01'
    """),
        {"i": str(riid)},
    ).first()
    assert row.in_fno_ban_list is True


def test_upserter_clears_flag_when_symbol_removed_from_ban(tmp_db_session):
    """A symbol removed from the daily list gets in_fno_ban_list = False."""
    riid = uuid.uuid4()
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'IDEA') ON CONFLICT DO NOTHING;
        INSERT INTO atlas.atlas_governance_daily (instrument_id, date, in_fno_ban_list)
        VALUES (:i, '2024-06-01', true)
    """),
        {"i": str(riid)},
    )
    upserter = FnoBanUpserter(tmp_db_session)
    # IDEA not in today's ban set
    upserter.upsert(date(2024, 6, 1), set())
    row = tmp_db_session.execute(
        text(
            "SELECT in_fno_ban_list FROM atlas.atlas_governance_daily "
            "WHERE instrument_id = :i AND date = '2024-06-01'"
        ),
        {"i": str(riid)},
    ).first()
    assert row.in_fno_ban_list is False
