"""Real-data tests for the household roll-up + succession-flag engine
(Rule #0: no fixtures — every assertion runs against the live wealth.* tables).
Client ids are resolved by name via SQL in the test itself — never hardcoded."""
import sys

sys.path.insert(0, "scripts/wealth")

from build_household import compute_all  # noqa: E402
from engine_common import connect  # noqa: E402


def _rows():
    conn = connect()
    return conn, compute_all(conn)


def test_one_row_per_client():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select count(*) from wealth.clients")
    (n,) = cur.fetchone()
    assert len(rows) == n


def test_household_count_in_expected_range():
    """Brief's ballpark: ~120-160 households across 234 clients (real data:
    242 clients). The unconditional surname+family_group edge alone produced
    ~111 households because it dragged the two RM-territory mega-clusters
    inside the 191931 batch (Shah 38, Patel 27 — see build_household.py
    docstring) into two giant households instead of many small ones. Fixed
    by size-gating that edge at _SURNAME_CLUSTER_MAX (8): clusters above the
    gate no longer merge on surname alone, only on a genuine joint_holders
    link, which splits the two mega-clusters back into their real family
    sub-groups + singletons while leaving every genuine small family
    (Zinzuvadia, Amin, etc.) untouched. Lands the count back inside the
    brief's original range."""
    _, rows = _rows()
    n_households = len({r["household_id"] for r in rows})
    assert 120 <= n_households <= 160, f"expected ~120-160 households, got {n_households}"


def test_zinzuvadia_cluster_resolves_to_one_household_with_ge_3_members():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select client_id from wealth.clients where full_name ilike '%zinzuvadia%'")
    ids = {r[0] for r in cur.fetchall()}
    assert len(ids) >= 3, "expected the known Zinzuvadia cluster (>=3 real clients) in wealth.clients"

    by_id = {r["client_id"]: r for r in rows}
    household_ids = {by_id[i]["household_id"] for i in ids if i in by_id}
    assert len(household_ids) == 1, f"Zinzuvadia clients split across households: {household_ids}"
    members = by_id[next(iter(ids))]["members"]
    assert members >= 3, f"Zinzuvadia household has only {members} members"


def test_amin_family_shows_transmission_seen():
    """Prafulbhai Amin is a deceased-departed client; the household he belongs
    to (resolved by surname/family_group, not a hardcoded id) must carry
    transmission_seen from whichever member's ledger records the event."""
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select client_id from wealth.clients where full_name ilike '%prafulbhai%amin%'")
    praful_ids = {r[0] for r in cur.fetchall()}
    assert praful_ids, "expected the deceased-departed Prafulbhai Amin client in wealth.clients"

    by_id = {r["client_id"]: r for r in rows}
    flags = {by_id[i]["succession_flag"] for i in praful_ids if i in by_id}
    assert "transmission_seen" in flags, f"Prafulbhai Amin household flag(s): {flags}"


def test_succession_flag_domain():
    _, rows = _rows()
    domain = {"transmission_seen", "single_holder_concentrated", "none"}
    for r in rows:
        assert r["succession_flag"] in domain, f"client {r['client_id']}: bad flag {r['succession_flag']!r}"


def test_household_mv_matches_ledger_blocks_sum():
    conn, rows = _rows()
    cur = conn.cursor()
    hh_id = rows[0]["household_id"]
    members = [r["client_id"] for r in rows if r["household_id"] == hh_id]
    cur.execute(
        "select coalesce(sum(market_value),0) from wealth.ledger_blocks where client_id = any(%s)",
        (members,),
    )
    (expected,) = cur.fetchone()
    assert round(float(expected), 2) == round(float(rows[0]["household_mv"]), 2)


def test_no_mega_household_dominates_the_book():
    """Sanity guard against an over-aggressive surname match absorbing a
    huge share of the book into one household (common-surname false merge)."""
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select coalesce(sum(market_value),0) from wealth.ledger_blocks")
    (total,) = cur.fetchone()
    total = float(total)
    by_hh = {r["household_id"]: float(r["household_mv"]) for r in rows}
    biggest = max(by_hh.values())
    assert biggest / total < 0.30, f"largest household is {biggest / total:.1%} of the book"
