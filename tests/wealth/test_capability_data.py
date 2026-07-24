"""Real-data tests for the capability_app data layer (Task 1: Q1/Q2/Q3/Q6 +
client index). Rule #0: every assertion runs against the live wealth.*/
atlas_foundation.* tables via engine_common.connect() — no fixtures, no mocks.
"""

import json
import sys

sys.path.insert(0, "scripts/wealth")

from capability_app.data import fetch_book
from capability_app.data_holdings import MANDATE_LEGS, q1_ownership, q2_label_check
from capability_app.data_holdings_overlap import (
    OVERLAP_DUPLICATE_DEFAULT,
    OVERLAP_DUPLICATE_KEY,
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


def test_fetch_book_returns_all_task1_keys_and_is_json_safe():
    conn = _conn()
    try:
        data = fetch_book(conn)
    finally:
        conn.close()
    for key in ("q1", "q2", "q3", "q6", "client_index"):
        assert key in data, f"fetch_book missing {key!r}"
    json.dumps(data, allow_nan=False)  # raises ValueError if any NaN/Inf slipped through
