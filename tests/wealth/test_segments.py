"""Real-data tests for the behaviour segmentation engine (Rule #0: no
fixtures — every assertion runs against the live wealth.* tables)."""

import sys
from decimal import Decimal

import pytest

sys.path.insert(0, "scripts/wealth")

from build_segments import SEGMENTS, compute_all
from engine_common import connect


def _rows():
    conn = connect()
    return conn, compute_all(conn)


def _independent_whatif(cur, cid) -> Decimal:
    """Re-derive whatif_rs straight from source tables, independent of
    build_segments.py: sum of ONLY the >=0 cost components among
    {panic_loss_out_rs, div_leak_rs, cf_sip_alive_rs} — a negative component
    is dropped, not subtracted."""
    cur.execute(
        "select panic_loss_out_rs, div_leak_rs from wealth.client_behaviour where client_id = %s",
        (cid,),
    )
    row = cur.fetchone()
    p = row[0] if row and row[0] is not None else Decimal(0)
    d = row[1] if row and row[1] is not None else Decimal(0)
    cur.execute("select cf_sip_alive_rs from wealth.counterfactuals where client_id = %s", (cid,))
    row = cur.fetchone()
    c = row[0] if row and row[0] is not None else Decimal(0)
    return sum(x for x in (p, d, c) if x >= 0)


def test_segment_counts_sum_to_client_count():
    """Partition invariant: every client in scope gets exactly one primary
    segment, and the segments cover all of wealth.clients."""
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select count(*) from wealth.clients")
    (n_clients,) = cur.fetchone()

    assert len(rows) == n_clients
    counts = {}
    for r in rows:
        assert r["segment"] in SEGMENTS, f"unknown segment {r['segment']!r}"
        counts[r["segment"]] = counts.get(r["segment"], 0) + 1
    assert sum(counts.values()) == n_clients
    conn.close()


def test_top_panic_loss_client_lands_in_crash_sellers():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute(
        "select client_id from wealth.client_behaviour "
        "order by panic_loss_out_rs desc nulls last limit 1"
    )
    (cid,) = cur.fetchone()
    got = next(r["segment"] for r in rows if r["client_id"] == cid)
    assert got == "Crash Sellers", (
        f"top panic_loss_out_rs client {cid} landed in {got!r}, not Crash Sellers"
    )
    conn.close()


def test_client_with_no_behaviour_and_no_benchmark_is_too_new():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute(
        """select c.client_id from wealth.clients c
           left join wealth.client_behaviour b using (client_id)
           left join wealth.client_benchmark k using (client_id)
           where b.client_id is null and k.client_id is null
           order by c.client_id limit 1"""
    )
    row = cur.fetchone()
    assert row is not None, "expected at least one client with no behaviour AND no benchmark row"
    (cid,) = row
    got = next(r["segment"] for r in rows if r["client_id"] == cid)
    assert got == "Too New to Tell", f"client {cid} (no behaviour, no benchmark) landed in {got!r}"
    conn.close()


def test_whatif_rs_matches_independent_sql_sum():
    """whatif_rs = sum of the client's >=0 cost components — a negative
    component must be DROPPED, not subtracted. Recompute it straight from
    source tables and compare, for two real clients:
      1. an all-positive-component client (the common case), and
      2. the client with a genuinely negative component (proves the >=0
         filter actually matters — dropping it would change the sum)."""
    conn, rows = _rows()
    cur = conn.cursor()

    cur.execute(
        "select client_id from wealth.client_behaviour "
        "where panic_loss_out_rs > 0 order by client_id limit 1"
    )
    row = cur.fetchone()
    assert row is not None, "expected at least one client with panic_loss_out_rs > 0"
    (positive_cid,) = row

    cur.execute(
        "select client_id from wealth.counterfactuals "
        "where cf_sip_alive_rs < 0 order by client_id limit 1"
    )
    row = cur.fetchone()
    if row is None:
        pytest.skip("no client with a negative cost component (cf_sip_alive_rs < 0) in the DB")
    (negative_cid,) = row

    for cid in (positive_cid, negative_cid):
        expected = _independent_whatif(cur, cid)
        got = next(r["whatif_rs"] for r in rows if r["client_id"] == cid)
        assert got == round(expected), (
            f"client {cid}: whatif_rs {got} != independent sum {round(expected)}"
        )

    conn.close()
