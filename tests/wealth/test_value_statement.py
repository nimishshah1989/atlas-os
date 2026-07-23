"""Real-data tests for the per-client value statement engine (Rule #0: no
fixtures — every assertion runs against the live wealth.* tables)."""
import sys

sys.path.insert(0, "scripts/wealth")

from build_value_statement import compute_all  # noqa: E402
from engine_common import connect  # noqa: E402


def _rows():
    conn = connect()
    return conn, compute_all(conn)


def test_one_row_per_client():
    conn, rows = _rows()
    assert len(rows) > 150
    cur = conn.cursor()
    cur.execute("select count(*) from wealth.clients")
    assert len(rows) == cur.fetchone()[0]


def test_sip_discipline_positive_somewhere():
    _, rows = _rows()
    some_sip = [r for r in rows if r["sip_discipline_rs"] > 0]
    assert some_sip, "book has thousands of SIP txns inside drawdown windows; discipline value must exist"


def test_all_components_nonnegative():
    _, rows = _rows()
    keys = ("sip_discipline_rs", "staying_power_rs", "advice_outcome_rs",
            "fee_save_yr_rs", "tax_headroom_rs", "coaching_opportunity_rs")
    for r in rows:
        for k in keys:
            assert r[k] >= 0, f"client {r['client_id']}: {k}={r[k]} < 0"


def test_advice_outcome_matches_independent_sql():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute(
        "select client_id, sum(alpha_1y_rs) from wealth.advice_ledger "
        "group by 1 having sum(alpha_1y_rs) > 0 order by 1 limit 1"
    )
    cid, expected = cur.fetchone()
    got = next(r["advice_outcome_rs"] for r in rows if r["client_id"] == cid)
    assert got == round(float(expected))


def test_coaching_opportunity_nonempty_for_panic_cohort():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select count(*) from wealth.client_behaviour where panic_share >= 0.10")
    (panic_cohort,) = cur.fetchone()
    assert panic_cohort > 0, "expected a real drawdown-seller cohort in wealth.client_behaviour"

    flagged = [r for r in rows if r["coaching_opportunity_rs"] > 100_000]
    assert flagged, "142-ish drawdown-sellers exist; coaching opportunity must be non-empty"


def test_staying_power_zero_for_panic_clients():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select client_id from wealth.client_behaviour where panic_share >= 0.10 limit 1")
    (cid,) = cur.fetchone()
    got = next(r["staying_power_rs"] for r in rows if r["client_id"] == cid)
    assert got == 0
