"""D1: PIT Nifty 500 membership ingest + diff-to-state."""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import text

from atlas.data_prereqs.v6.membership import (
    MembershipIngester,
    diff_snapshots,
    parse_reconstitution_snapshot,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nifty500_reconstitution_2024_09.json"


def test_parse_reconstitution_snapshot_yields_symbol_set():
    payload = json.loads(FIXTURE.read_text())
    snap = parse_reconstitution_snapshot(payload)
    assert snap.effective_date == date(2024, 9, 30)
    assert snap.symbols == frozenset({"RELIANCE", "TCS", "INFY"})
    assert snap.index_name == "NIFTY 500"


def test_diff_two_snapshots_produces_adds_and_drops():
    prior_symbols = {"RELIANCE", "TCS", "FOO"}
    curr_symbols = {"RELIANCE", "TCS", "INFY"}
    adds, drops = diff_snapshots(prior_symbols, curr_symbols)
    assert adds == {"INFY"}
    assert drops == {"FOO"}


def test_apply_diff_updates_valid_to_for_drops(monkeypatch, tmp_db_session):
    ing = MembershipIngester(tmp_db_session)
    riid, tiid = uuid.uuid4(), uuid.uuid4()
    tmp_db_session.execute(
        text("""
        INSERT INTO atlas.atlas_index_membership
            (index_name, instrument_id, valid_from, valid_to)
        VALUES ('NIFTY 500', :r, '2024-03-30', NULL),
               ('NIFTY 500', :t, '2024-03-30', NULL)
    """),
        {"r": str(riid), "t": str(tiid)},
    )
    monkeypatch.setattr(
        ing,
        "_resolve_symbol_to_iid",
        lambda s: {"RELIANCE": riid, "TCS": tiid}[s],
    )
    ing.apply_diff(
        index_name="NIFTY 500",
        effective_date=date(2024, 9, 30),
        adds=set(),
        drops={"TCS"},
    )
    row = tmp_db_session.execute(
        text("SELECT valid_to FROM atlas.atlas_index_membership " "WHERE instrument_id = :i"),
        {"i": str(tiid)},
    ).first()
    assert row.valid_to == date(2024, 9, 30)


def test_apply_diff_opens_new_row_for_adds(monkeypatch, tmp_db_session):
    ing = MembershipIngester(tmp_db_session)
    iiid = uuid.uuid4()
    monkeypatch.setattr(ing, "_resolve_symbol_to_iid", lambda s: iiid)
    ing.apply_diff(
        index_name="NIFTY 500",
        effective_date=date(2024, 9, 30),
        adds={"INFY"},
        drops=set(),
    )
    row = tmp_db_session.execute(
        text(
            "SELECT valid_from, valid_to FROM atlas.atlas_index_membership "
            "WHERE instrument_id = :i"
        ),
        {"i": str(iiid)},
    ).first()
    assert row.valid_from == date(2024, 9, 30)
    assert row.valid_to is None
