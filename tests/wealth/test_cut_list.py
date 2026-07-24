"""Cut-list engine (Prompt 7) — asserts on REAL wealth.cut_list rows (Rule #0).

No synthetic inputs: every client and every number here is pulled live from the
engine's own output and cross-checked against an independent SQL sum over the
real wealth.lots / wealth.client_fund_overlap / wealth.holdings tables.
Run: .venv/bin/python -m pytest tests/wealth/test_cut_list.py -v
"""

import os

import psycopg2

DSN = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
CLEAN_NOTE = "nothing to cut — portfolio holds genuinely different bets"


def _conn():
    return psycopg2.connect(DSN)


def test_heavy_overlap_client_gets_tax_efficient_ordered_cuts():
    conn = _conn()
    cur = conn.cursor()
    # heaviest real cut list the engine produced (psycopg2 decodes jsonb -> list)
    cur.execute(
        "select client_id, cut from wealth.cut_list "
        "where jsonb_array_length(cut) > 0 "
        "order by jsonb_array_length(cut) desc limit 1"
    )
    row = cur.fetchone()
    assert row is not None, "engine produced no non-empty cut list"
    cid, cut = row

    # redundancy is real: the client actually has a >50% look-through overlap pair
    cur.execute(
        "select count(*) from wealth.client_fund_overlap where client_id = %s and overlap_pct > 50",
        (cid,),
    )
    assert cur.fetchone()[0] > 0, f"client {cid} cut but has no >50% pair"

    # unwind_order is dense 1..n and ascending in exit_tax (cheapest-to-exit first)
    orders = [c["unwind_order"] for c in cut]
    assert orders == list(range(1, len(cut) + 1)), orders
    taxes = [c["exit_tax_rs"] for c in cut]
    assert taxes == sorted(taxes), f"unwind not ascending in exit_tax: {taxes}"

    # every cut fund's exit_tax_rs == independent SQL sum over its OPEN lots
    for c in cut:
        cur.execute(
            "select coalesce(sum(tax_if_sold_now), 0) from wealth.lots "
            "where client_id = %s and scheme_id = %s and status = 'open'",
            (cid, c["scheme_id"]),
        )
        indep = float(cur.fetchone()[0])
        assert abs(indep - c["exit_tax_rs"]) < 0.01, (cid, c, indep)
        assert "redundant" in c["reason"], c["reason"]


def test_diversified_client_gets_empty_cut_and_plain_note():
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "select client_id, note, cut from wealth.cut_list where note = %s limit 1",
        (CLEAN_NOTE,),
    )
    row = cur.fetchone()
    assert row is not None, "no client hit the evidence-gate clean note"
    cid, _note, cut = row
    assert cut == [], f"clean client {cid} still has cuts: {cut}"
    # genuinely diversified: no >50% overlap pair backs the plain-language note
    cur.execute(
        "select count(*) from wealth.client_fund_overlap where client_id = %s and overlap_pct > 50",
        (cid,),
    )
    assert cur.fetchone()[0] == 0, f"client {cid} has a >50% pair but was called clean"


def test_min_fund_count_bounded_and_keep_disjoint_from_cut():
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """select cl.client_id, cl.min_fund_count, cl.keep, cl.cut,
                  (select count(distinct scheme_id) from wealth.holdings h
                   where h.client_id = cl.client_id and h.market_value > 0)
           from wealth.cut_list cl"""
    )
    rows = cur.fetchall()
    assert rows, "cut_list is empty"
    for cid, mfc, keep, cut, held in rows:
        assert 1 <= mfc <= held, (cid, mfc, held)
        keep_names = {k["fund"] for k in keep}
        cut_names = {c["fund"] for c in cut}
        assert keep_names.isdisjoint(cut_names), (cid, keep_names & cut_names)
