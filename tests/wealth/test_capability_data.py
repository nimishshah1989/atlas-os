"""Real-data tests for the capability_app data layer (Task 1: Q1/Q2/Q3/Q6 +
client index; Task 2: Q4/Q5/Q7, B1-B5, client_index annotation, Client 360).
Rule #0: every assertion runs against the live wealth.*/atlas_foundation.*
tables via engine_common.connect() — no fixtures, no mocks.
"""

import json
import sys

sys.path.insert(0, "scripts/wealth")

from capability_app.data import fetch_book
from capability_app.data_behaviour import (
    annotate_behaviour_flags,
    annotate_client_index,
    b1_advice_vs_index,
    b2_behaviour_gap,
    b3_panic_pattern,
    b4_advice_switches,
    b5_what_if_machine,
)
from capability_app.data_client360 import (
    client_header,
    client_sector_lookthrough,
    client_timeline,
    crisis_windows_once,
)
from capability_app.data_client360_behaviour import client_360, client_360_all
from capability_app.data_holdings import MANDATE_LEGS, q1_ownership, q2_label_check
from capability_app.data_holdings_fees import q4_fees, q5_fund_performance, q7_cut_list
from capability_app.data_holdings_overlap import (
    OVERLAP_DUPLICATE_DEFAULT,
    OVERLAP_DUPLICATE_KEY,
    _seed_overlap_threshold,
    client_index_rows,
    q3_overlap,
    q6_bloat_check,
)
from engine_common import connect

# client_id=1: confirmed (via live psql) to have real rows in wealth.holdings,
# a wealth.fund_label_check verdict='mismatch' join, wealth.client_fund_overlap
# pairs above the 50% threshold, and a wealth.client_segments row.
SAMPLE_CLIENT = 1

HONESTY_VALUES = {"exact", "estimate", "upper bound", "floor"}


def _assert_working_shape(working: dict, *, allow_null_honesty: bool = False) -> None:
    for key in ("inputs", "rule", "assumptions", "steps", "sample_rows", "sample_of", "honesty"):
        assert key in working, f"working object missing {key!r}"
    assert isinstance(working["inputs"], list)
    assert isinstance(working["rule"], str) and working["rule"]
    assert isinstance(working["assumptions"], list)
    for a in working["assumptions"]:
        assert a["bias"], "every assumption must state its bias direction"
    assert isinstance(working["steps"], list)
    assert isinstance(working["sample_rows"], list)
    assert len(working["sample_rows"]) <= 20
    assert isinstance(working["sample_of"], int)
    if allow_null_honesty:
        assert working["honesty"] is None or working["honesty"] in HONESTY_VALUES
    else:
        assert working["honesty"] in HONESTY_VALUES, working["honesty"]


def _conn():
    return connect()


def test_q1_ownership_real_data_and_working_shape():
    conn = _conn()
    try:
        q1 = q1_ownership(conn)
    finally:
        conn.close()
    assert q1["total_value_rs"] > 0
    assert q1["n_funds"] > 0
    assert q1["n_amcs"] > 0
    assert q1["funds_per_client_hist"]["n"] > 0
    assert q1["funds_per_client_hist"]["median"] is not None
    assert 1 <= len(q1["top10_funds"]) <= 10
    for row in q1["top10_funds"]:
        assert row["share_pct"] is None or 0 <= row["share_pct"] <= 100
    assert q1["verdict"].startswith("₹")
    assert q1["honesty"] == "exact"
    _assert_working_shape(q1["working"])
    assert q1["working"]["sample_of"] > 0


def test_q2_label_check_real_data_and_working_shape():
    conn = _conn()
    try:
        q2 = q2_label_check(conn)
    finally:
        conn.close()
    assert q2["mismatch_value_rs"] > 0, "book should have real ₹ sitting in mismatch funds"
    assert q2["n_mismatch_funds"] > 0
    assert q2["as_of_month"] != "unknown"
    assert q2["as_of_min"] <= q2["as_of_max"]
    assert q2["category_bars"], "at least one SEBI category should have held funds"
    for bar in q2["category_bars"]:
        assert bar["category"] in MANDATE_LEGS
        assert bar["n_mismatch"] <= bar["n_funds"]
        for leg in bar["legs"]:
            assert 0 <= leg["actual_pct"] <= 100
            assert 0 <= leg["mandate_pct"] <= 100
    assert q2["offenders"], "at least one offender fund expected"
    for row in q2["offenders"]:
        assert row["shortfall_pct"] >= 0
        assert row["value_rs"] > 0
    assert "doesn't match their contents" in q2["verdict"]
    assert q2["honesty"] == "exact"
    _assert_working_shape(q2["working"])


def test_q3_overlap_real_data_and_working_shape():
    conn = _conn()
    try:
        q3 = q3_overlap(conn)
    finally:
        conn.close()
    assert q3["threshold_pct"] == OVERLAP_DUPLICATE_DEFAULT
    assert 0 <= q3["median_overlap_pct"] <= 100
    assert q3["pairs_above_threshold"] > 0
    assert q3["rupee_duplicated_rs"] > 0
    assert len(q3["top15_funds"]) == 15
    assert len(q3["top15_pairwise"]) == 15 * 14 // 2
    for pair in q3["top15_pairwise"]:
        assert 0 <= pair["overlap_pct"] <= 100
    assert q3["top15_stock_matrix"], "top-15 book-wide funds should share some stocks"
    for row in q3["top15_stock_matrix"]:
        assert row["n_funds_holding"] >= 2, "evidence table must only show SHARED stocks"
    assert "overlap more than" in q3["verdict"]
    assert q3["honesty"] == "estimate"
    _assert_working_shape(q3["working"])
    assert q3["working"]["sample_of"] == q3["pairs_above_threshold"]


def test_q3_seeds_the_new_atlas_threshold_row():
    """Constraint 5: the >50% duplicate-pair cutoff must be a real row in
    atlas_foundation.atlas_thresholds, not a Python literal."""
    conn = _conn()
    try:
        q3_overlap(conn)  # seeds (idempotently) if absent
        cur = conn.cursor()
        cur.execute(
            "select threshold_value, category, is_active "
            "from atlas_foundation.atlas_thresholds where threshold_key = %s",
            (OVERLAP_DUPLICATE_KEY,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None, "wealth_overlap_duplicate_pct row must exist after seeding"
    value, category, is_active = row
    assert float(value) == OVERLAP_DUPLICATE_DEFAULT
    assert category == "wealth"
    assert is_active is True


def test_q6_bloat_check_is_an_honest_empty_state():
    q6 = q6_bloat_check()
    assert "don't have this data" in q6["message"]
    working = q6["working"]
    assert working["inputs"] == []
    assert working["sample_rows"] == []
    assert working["sample_of"] == 0
    assert working["rule"] == "no factsheet/SID feed exists in the pipeline"
    assert working["honesty"] is None
    _assert_working_shape(working, allow_null_honesty=True)


def test_client_index_rows_real_data():
    conn = _conn()
    try:
        idx = client_index_rows(conn)
    finally:
        conn.close()
    assert idx["n_clients"] > 0
    by_id = {r["client_id"]: r for r in idx["rows"]}
    assert SAMPLE_CLIENT in by_id, "SAMPLE_CLIENT must resolve in the client index"
    row = by_id[SAMPLE_CLIENT]
    assert row["name"]
    assert row["value_rs"] > 0
    assert row["fund_count"] > 0
    assert row["off_label_flag"] is True  # confirmed via psql: client 1 holds mismatch funds
    assert row["overlap_flag"] is True  # confirmed via psql: client 1 has pairs > 50%
    assert row["segment"]
    for r in idx["rows"]:
        assert (r["off_label_rs"] or 0) >= 0


def test_q4_fees_real_data_and_working_shape():
    conn = _conn()
    try:
        q4 = q4_fees(conn)
    finally:
        conn.close()
    # confirmed via psql: 29 clients have fee_save_yr_rs > 0
    assert q4["n_clients_paying"] == 29
    assert q4["total_fee_save_yr_rs"] > 0
    assert q4["dumbbell"], "at least one category should have held funds with a real ER"
    for row in q4["dumbbell"]:
        assert row["n_held_funds"] > 0
        assert row["regular_actual_pct"] is not None and row["regular_actual_pct"] > 0
    assert q4["honesty"] == "estimate"
    _assert_working_shape(q4["working"])


def test_q5_fund_performance_real_data_and_working_shape():
    conn = _conn()
    try:
        q5 = q5_fund_performance(conn)
    finally:
        conn.close()
    assert q5["n_funds"] > 0
    # confirmed via psql: 56 held funds have beat_count < windows/2
    assert q5["n_laggard_funds"] == 56
    assert q5["laggard_value_rs"] > 0
    for fund in q5["funds"]:
        assert fund["verdict"] in ("scored", "insufficient_history")
        if fund["beat_count"] is not None and fund["windows"]:
            assert fund["is_laggard"] == (fund["beat_count"] < fund["windows"] / 2.0)
    assert q5["honesty"] == "exact"
    _assert_working_shape(q5["working"])


def test_q7_cut_list_real_data_and_working_shape():
    conn = _conn()
    try:
        q7 = q7_cut_list(conn)
    finally:
        conn.close()
    # confirmed via psql: 216 rows in wealth.cut_list, 48 have a non-empty cut list
    assert q7["n_clients"] == 216
    assert q7["n_with_cut"] == 48
    assert q7["total_cut_value_rs"] > 0
    assert "duplicate" in q7["chip_counts"] or "laggard" in q7["chip_counts"]
    assert "expensive" not in q7["chip_counts"], "no such chip exists in weak_funds() vocabulary"
    assert q7["sankey"], "at least one cut fund should have a keep-side overlap partner"
    for edge in q7["sankey"]:
        assert edge["n_clients"] > 0
    assert q7["honesty"] == "estimate"
    _assert_working_shape(q7["working"])
    # Finding 1 (review of f5c101c9): Q7's verdict must wire in a real
    # TER-implied fee-save figure (shared expense-ratio lookup with q4_fees)
    # and a duplication-removed % (derived from the same highest-overlap
    # keep-partner data used for the sankey) — not just cut-value/exit-tax.
    assert q7["total_cut_fee_rs"] > 0, "fee delta must not be zero when there are cut funds"
    assert 0 < q7["duplication_removed_pct"] <= 100
    assert "saves" in q7["verdict"] and "/yr in fees" in q7["verdict"]
    assert "duplication" in q7["verdict"]
    assert "Cutting" in q7["verdict"]


def test_b1_advice_vs_index_real_data_and_working_shape():
    conn = _conn()
    try:
        b1 = b1_advice_vs_index(conn)
    finally:
        conn.close()
    # confirmed via psql: 212 client_benchmark rows have a non-null alpha
    assert b1["n_clients"] == 212
    assert b1["n_clean"] > 0
    assert 0 <= b1["n_beating_clean"] <= b1["n_clean"]
    assert b1["honesty"] == "exact"
    _assert_working_shape(b1["working"])


def test_b2_behaviour_gap_real_data_and_working_shape():
    conn = _conn()
    try:
        b2 = b2_behaviour_gap(conn)
    finally:
        conn.close()
    # confirmed via psql: 3336 rows in wealth.behaviour_gap
    assert b2["n_rows"] == 3336
    assert b2["total_gap_rs"] != 0
    assert b2["honesty"] == "exact"
    _assert_working_shape(b2["working"])


def test_b3_panic_pattern_real_data_and_working_shape():
    conn = _conn()
    try:
        b3 = b3_panic_pattern(conn)
    finally:
        conn.close()
    assert b3["n_windows"] > 0, "drawdown_windows() must find at least one real crash"
    assert len(b3["crisis_windows"]) == b3["n_windows"]
    assert b3["total_panic_loss_rs"] > 0
    assert b3["honesty"] == "exact"
    _assert_working_shape(b3["working"])


def test_b4_advice_switches_real_data_and_working_shape():
    conn = _conn()
    try:
        b4 = b4_advice_switches(conn)
    finally:
        conn.close()
    # confirmed via psql: 33312 advice_ledger rows, 992 advice_waves rows
    assert b4["n_switches"] == 33312
    assert b4["n_waves"] == 992
    assert b4["honesty"] == "estimate"
    _assert_working_shape(b4["working"])


def test_b5_what_if_machine_real_data_and_working_shape():
    conn = _conn()
    try:
        b5 = b5_what_if_machine(conn)
    finally:
        conn.close()
    # confirmed via psql: 234 rows in wealth.counterfactuals
    assert b5["n_clients"] == 234
    expected_honesty = {
        "cf_index_rs": "estimate",
        "cf_no_panic_rs": "upper bound",
        "cf_sip_alive_rs": "estimate",
        "cf_no_switch_rs": "estimate",
    }
    for key, honesty in expected_honesty.items():
        assert b5["scenarios"][key]["honesty"] == honesty
    assert b5["honesty"] == "estimate"
    _assert_working_shape(b5["working"])


def test_annotate_client_index_flags_sample_client():
    conn = _conn()
    try:
        idx = client_index_rows(conn)
        idx = annotate_client_index(conn, idx)
    finally:
        conn.close()
    by_id = {r["client_id"]: r for r in idx["rows"]}
    row = by_id[SAMPLE_CLIENT]
    # confirmed via psql: client 1 holds a fund with beat_count < windows/2,
    # and has fee_save_yr_rs == 0 (not above the median of paying clients)
    assert row["chronic_laggard_flag"] is True
    assert row["fees_above_median_flag"] is False
    for r in idx["rows"]:
        assert isinstance(r["chronic_laggard_flag"], bool)
        assert isinstance(r["fees_above_median_flag"], bool)


def test_annotate_behaviour_flags_sample_client():
    conn = _conn()
    try:
        idx = client_index_rows(conn)
        idx = annotate_client_index(conn, idx)
        idx = annotate_behaviour_flags(conn, idx)
    finally:
        conn.close()
    by_id = {r["client_id"]: r for r in idx["rows"]}
    row = by_id[SAMPLE_CLIENT]
    # confirmed via psql: client 1 has panic_share=0.12 (<=0.25), sip_streams=26
    # with sip_active=16 (some SIPs still running), and a switch count of 85
    # (< the book's own 90th-percentile cutoff ~383) — all three flags False.
    assert row["panic_seller_flag"] is False
    assert row["dead_sip_flag"] is False
    assert row["chronic_switcher_flag"] is False
    for r in idx["rows"]:
        assert isinstance(r["panic_seller_flag"], bool)
        assert isinstance(r["dead_sip_flag"], bool)
        assert isinstance(r["chronic_switcher_flag"], bool)
    # at least one client on each side of each flag — a threshold that never
    # fires (or always fires) would signal a bug in the cutoff, not a real finding.
    assert any(r["panic_seller_flag"] for r in idx["rows"])
    assert any(r["dead_sip_flag"] for r in idx["rows"])
    assert any(r["chronic_switcher_flag"] for r in idx["rows"])


def test_client_360_sample_client_all_sections_present():
    conn = _conn()
    try:
        crisis_windows = crisis_windows_once(conn)
        threshold = _seed_overlap_threshold(conn)
        page = client_360(conn, SAMPLE_CLIENT, crisis_windows=crisis_windows, threshold=threshold)
    finally:
        conn.close()
    for key in (
        "header",
        "timeline",
        "funds_table",
        "label_check",
        "sector_lookthrough",
        "overlap",
        "fees_and_cuts",
        "behaviour",
        "what_ifs",
    ):
        assert key in page, f"client_360 missing {key!r}"
    assert page["header"]["client_id"] == SAMPLE_CLIENT
    assert page["header"]["name"]
    assert page["header"].get("insufficient") is not True
    _assert_working_shape(page["header"]["working"])
    assert page["timeline"]["months"], "client 1 has real client_curves rows"
    _assert_working_shape(page["timeline"]["working"])
    assert page["funds_table"]["n_funds"] > 0  # client 1 has real held funds
    _assert_working_shape(page["funds_table"]["working"])
    _assert_working_shape(page["label_check"]["working"], allow_null_honesty=True)
    _assert_working_shape(page["overlap"]["working"])
    assert page["overlap"]["n_pairs"] > 0  # client 1 has real overlap pairs (confirmed via psql)
    _assert_working_shape(page["fees_and_cuts"]["working"])
    _assert_working_shape(page["what_ifs"]["working"])
    behaviour = page["behaviour"]
    if not behaviour.get("insufficient"):
        _assert_working_shape(behaviour["working"])


def test_client_header_direct_and_client_timeline_direct():
    """Direct unit coverage of the two data_client360.py functions not
    otherwise exercised standalone by the client_360 composition test."""
    conn = _conn()
    try:
        crisis_windows = crisis_windows_once(conn)
        header = client_header(conn, SAMPLE_CLIENT)
        timeline = client_timeline(conn, SAMPLE_CLIENT, crisis_windows)
        sector = client_sector_lookthrough(conn, SAMPLE_CLIENT)
    finally:
        conn.close()
    assert header["gross_in_rs"] > 0
    assert header["honesty"] == "exact"
    assert timeline["coverage_pct"] is not None
    assert sector["total_exposure_rs"] > 0  # client 1 has real client_stock_exposure rows
    assert sector["honesty"] == "exact"


def test_client_360_all_contains_sample_client_and_is_json_safe():
    """Heavier end-to-end check: runs the whole per-client loop once (~217
    clients) and confirms it's JSON-safe. Deliberately only one test exercises
    the full loop — per-client sections are covered individually above."""
    conn = _conn()
    try:
        pages = client_360_all(conn)
    finally:
        conn.close()
    assert SAMPLE_CLIENT in pages
    assert len(pages) > 0
    json.dumps(pages, allow_nan=False)


def test_fetch_book_returns_all_task1_and_task2_keys_and_is_json_safe():
    conn = _conn()
    try:
        data = fetch_book(conn)
    finally:
        conn.close()
    for key in (
        "q1",
        "q2",
        "q3",
        "q4",
        "q5",
        "q6",
        "q7",
        "b1",
        "b2",
        "b3",
        "b4",
        "b5",
        "client_index",
        "client360",
    ):
        assert key in data, f"fetch_book missing {key!r}"
    assert SAMPLE_CLIENT in data["client360"]
    by_id = {r["client_id"]: r for r in data["client_index"]["rows"]}
    assert "chronic_laggard_flag" in by_id[SAMPLE_CLIENT]
    assert "fees_above_median_flag" in by_id[SAMPLE_CLIENT]
    assert "panic_seller_flag" in by_id[SAMPLE_CLIENT]
    assert "dead_sip_flag" in by_id[SAMPLE_CLIENT]
    assert "chronic_switcher_flag" in by_id[SAMPLE_CLIENT]
    # confirmed via psql: 210,634 rows in wealth.transactions, 1989-05-29 -> 2026-07-21
    assert data["n_transactions"] == 210634
    assert data["txn_years"] == 37
    json.dumps(data, allow_nan=False)  # raises ValueError if any NaN/Inf slipped through
