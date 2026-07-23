"""Real-data tests for the per-client audit-pack assembler (Rule #0: no
fixtures — every assertion runs against the live wealth.* tables). Clients
are resolved by query (highest-MV, a source-absent client), never hardcoded."""
import functools
import json
import sys

sys.path.insert(0, "scripts/wealth")

from build_audit_packs import SECTION_NAMES, compute_all  # noqa: E402
from engine_common import connect  # noqa: E402


@functools.lru_cache(maxsize=1)
def _packs():
    """compute_all() joins ~15 tables across the whole book; cache it once
    per test session instead of once per test (was 8x recompute -> 126s of
    DB load, starving the final test's DROP TABLE past statement_timeout)."""
    conn = connect()
    conn.autocommit = True  # else this connection sits idle-in-transaction for
    # the rest of the session (cached, reused by every test below), holding an
    # AccessShareLock on wealth.clients that queues behind main()'s DROP TABLE
    # (which needs AccessExclusiveLock on wealth.clients too, via the FK) until
    # statement_timeout kills it -- root cause of the flaky 120s hang below.
    rows = compute_all(conn)
    return conn, {r["client_id"]: r["payload"] for r in rows}


def _top_mv_client_ids(conn, n=3):
    cur = conn.cursor()
    cur.execute(
        """select distinct on (client_id) client_id, mv_total from wealth.client_reports
           order by client_id, as_on_date desc"""
    )
    latest = cur.fetchall()
    latest.sort(key=lambda r: (r[1] or 0), reverse=True)
    return [cid for cid, _ in latest[:n]]


def test_section_order_is_the_spec_contract():
    assert SECTION_NAMES == [
        "map", "label_check", "overlap", "fees", "benchmark", "habits", "value", "actions",
    ]


def test_one_row_per_client():
    conn, packs = _packs()
    cur = conn.cursor()
    cur.execute("select count(*) from wealth.clients")
    (n,) = cur.fetchone()
    assert len(packs) == n


def test_top_3_mv_clients_all_8_sections_present_in_order_with_headline():
    """All 8 sections must be present, in the contract order, for each of the
    3 highest-MV clients. A section is either sufficient (carries a
    headline_value) or explicitly insufficient (carries a reason) — real
    data means even a whale client can be missing one source table (e.g. too
    few cash flows for the benchmark replay), and that must show up honestly,
    not be forced green."""
    conn, packs = _packs()
    for cid in _top_mv_client_ids(conn, 3):
        pack = packs[cid]
        assert list(pack.keys()) == SECTION_NAMES, f"client {cid}: section order {list(pack.keys())}"
        for name in SECTION_NAMES:
            section = pack[name]
            if section.get("insufficient") is True:
                assert isinstance(section.get("reason"), str) and section["reason"], \
                    f"client {cid}.{name}: insufficient with no reason"
            else:
                assert section.get("headline_value") is not None, f"client {cid}.{name}: missing headline_value"
        assert pack["map"]["total_mv"] > 0, f"client {cid}: map.total_mv not > 0"


def test_client_absent_from_client_benchmark_shows_insufficient_with_reason():
    conn, packs = _packs()
    cur = conn.cursor()
    cur.execute(
        "select client_id from wealth.clients where client_id not in "
        "(select client_id from wealth.client_benchmark) limit 1"
    )
    (cid,) = cur.fetchone()
    section = packs[cid]["benchmark"]
    assert section["insufficient"] is True
    assert isinstance(section["reason"], str) and section["reason"]


def test_client_absent_from_client_overlap_shows_insufficient_with_reason():
    conn, packs = _packs()
    cur = conn.cursor()
    cur.execute(
        "select client_id from wealth.clients where client_id not in "
        "(select client_id from wealth.client_overlap) limit 1"
    )
    (cid,) = cur.fetchone()
    section = packs[cid]["overlap"]
    assert section["insufficient"] is True
    assert isinstance(section["reason"], str) and section["reason"]


def test_no_flags_client_gets_true_zero_fee_save_not_insufficient():
    """fee_save_yr_rs comes from wealth.value_statements, which defaults every
    client to 0 — a clean client (no closet-index flag) must show 0, not
    'insufficient': the honesty-rail exception the brief calls out."""
    conn, packs = _packs()
    cur = conn.cursor()
    cur.execute(
        "select client_id from wealth.clients where client_id not in "
        "(select client_id from wealth.client_flags) limit 1"
    )
    row = cur.fetchone()
    assert row, "expected at least one client with no client_flags rows"
    (cid,) = row
    section = packs[cid]["fees"]
    assert section.get("insufficient") is not True
    assert section["fee_save_yr_rs"] == 0
    assert section["headline_value"] == 0


def test_payload_is_strict_json_no_nan():
    """json.dumps must succeed without allow_nan (default already forbids
    non-finite floats from round-tripping cleanly; assert no NaN/Infinity
    token appears in the serialized text, which allow_nan=True would emit)."""
    conn, packs = _packs()
    cid = _top_mv_client_ids(conn, 1)[0]
    text = json.dumps(packs[cid], default=str)
    assert "NaN" not in text and "Infinity" not in text


def test_payload_size_sane():
    conn, packs = _packs()
    for cid, payload in packs.items():
        size = len(json.dumps(payload, default=str))
        assert size < 100_000, f"client {cid}: payload {size} bytes"


def test_written_table_matches_computed_rows():
    """End-to-end: run main() (its own connection + its own compute_all())
    writes wealth.audit_packs; row count + a spot payload match the cached
    in-process rows. Reuses the cached _packs() connection for the read-back
    rather than opening yet another one."""
    import build_audit_packs

    conn, packs = _packs()
    rc = build_audit_packs.main()
    assert rc == 0

    cur = conn.cursor()
    cur.execute("select count(*) from wealth.audit_packs")
    (n,) = cur.fetchone()
    assert n == len(packs)

    cid = _top_mv_client_ids(conn, 1)[0]
    cur.execute("select payload, prose from wealth.audit_packs where client_id = %s", (cid,))
    payload, prose = cur.fetchone()
    # jsonb does not preserve key-insertion order on round-trip (Postgres
    # re-serializes it) -- set equality here, exact-order is asserted
    # in-process (pre-insert) by test_section_order_is_the_spec_contract
    # and test_top_3_mv_clients_...; consumers import SECTION_NAMES.
    assert set(payload.keys()) == set(SECTION_NAMES)
    assert prose is None
