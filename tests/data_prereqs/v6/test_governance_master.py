"""D6: Auditor + promoter group scrape into atlas_governance_master."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import text

from atlas.data_prereqs.v6.governance_master import (
    TOP_10_AUDITORS,
    GovernanceMasterUpserter,
    is_top_10_auditor,
    parse_screener_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "screener_company_sample.html"


def test_top_10_auditor_list_contains_expected():
    assert "Deloitte" in [a.split()[0] for a in TOP_10_AUDITORS]
    assert "BSR" in [a.split()[0] for a in TOP_10_AUDITORS]
    assert "Walker" in [a.split()[0] for a in TOP_10_AUDITORS]


def test_is_top_10_auditor_fuzzy_match():
    assert is_top_10_auditor("Deloitte Haskins & Sells LLP") is True
    assert is_top_10_auditor("BSR & Co. LLP") is True
    assert is_top_10_auditor("Shah Dhandharia & Co LLP") is False
    assert is_top_10_auditor(None) is False


def test_parse_screener_html_returns_dict():
    html = FIXTURE.read_text()
    out = parse_screener_html(html)
    assert out["promoter_group"] == "Adani Group"
    assert out["auditor_name"].startswith("Shah Dhandharia")


def test_upserter_writes_master_with_top_10_flag(tmp_db_session):
    iid = uuid.uuid4()
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_instrument_master (instrument_id, symbol)
        VALUES (:i, 'ADANIENT') ON CONFLICT DO NOTHING
    """),
        {"i": str(iid)},
    )
    upserter = GovernanceMasterUpserter(tmp_db_session)
    upserter.upsert(
        symbol="ADANIENT",
        promoter_group="Adani Group",
        auditor_name="Shah Dhandharia & Co LLP",
    )
    row = tmp_db_session.execute(
        text(
            "SELECT promoter_group, auditor_name, auditor_is_top_10 "
            "FROM atlas.atlas_governance_master WHERE instrument_id = :i"
        ),
        {"i": str(iid)},
    ).first()
    assert row.promoter_group == "Adani Group"
    assert row.auditor_name.startswith("Shah Dhandharia")
    assert row.auditor_is_top_10 is False
