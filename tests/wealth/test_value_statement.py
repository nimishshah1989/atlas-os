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


def test_five_components_nonnegative_advice_outcome_signed():
    """advice_outcome_rs is the one component allowed to be negative (true,
    signed alpha — a value statement must show underperforming switches, not
    hide them). The other five are spec-mandated floors."""
    _, rows = _rows()
    floored_keys = ("sip_discipline_rs", "staying_power_rs",
                    "fee_save_yr_rs", "tax_headroom_rs", "coaching_opportunity_rs")
    for r in rows:
        for k in floored_keys:
            assert r[k] >= 0, f"client {r['client_id']}: {k}={r[k]} < 0"
    assert any(r["advice_outcome_rs"] < 0 for r in rows), \
        "18 clients have net-negative alpha_1y_rs; advice_outcome_rs must surface it, not floor it"


def test_advice_outcome_matches_independent_sql_positive_client():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute(
        "select client_id, sum(alpha_1y_rs) from wealth.advice_ledger "
        "group by 1 having sum(alpha_1y_rs) > 0 order by 1 limit 1"
    )
    cid, expected = cur.fetchone()
    got = next(r["advice_outcome_rs"] for r in rows if r["client_id"] == cid)
    assert got == round(float(expected))


def test_advice_outcome_matches_independent_sql_negative_client():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute(
        "select client_id, sum(alpha_1y_rs) from wealth.advice_ledger "
        "group by 1 having sum(alpha_1y_rs) < 0 order by 1 limit 1"
    )
    cid, expected = cur.fetchone()
    got = next(r["advice_outcome_rs"] for r in rows if r["client_id"] == cid)
    assert got == round(float(expected)) < 0


def test_coaching_opportunity_nonempty_for_panic_cohort():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select count(*) from wealth.client_behaviour where panic_share >= 0.10")
    (panic_cohort,) = cur.fetchone()
    assert panic_cohort > 0, "expected a real drawdown-seller cohort in wealth.client_behaviour"

    flagged = [r for r in rows if r["coaching_opportunity_rs"] > 100_000]
    assert flagged, "142-ish drawdown-sellers exist; coaching opportunity must be non-empty"


def test_staying_power_below_current_holdings_value():
    """Regression guard for the per-window double-count bug: a growth-only
    slice of a position cannot exceed that position's entire current market
    value. Both sides come from the live DB — non-panic client set from
    wealth.client_behaviour (same definition compute_all uses), current
    holdings value from wealth.holdings' latest snapshot per client."""
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select client_id, panic_share from wealth.client_behaviour")
    non_panic = {cid for cid, share in cur.fetchall() if (share or 0) < 0.10}

    cur.execute(
        """with latest as (select client_id, max(report_id) rid from wealth.holdings group by 1)
           select coalesce(sum(h.market_value), 0)
           from wealth.holdings h join latest l on l.client_id = h.client_id and l.rid = h.report_id
           where h.client_id = any(%s)""",
        (list(non_panic),),
    )
    (current_mv,) = cur.fetchone()

    staying_power_total = sum(r["staying_power_rs"] for r in rows if r["client_id"] in non_panic)
    assert staying_power_total < float(current_mv), (
        f"staying_power_rs cohort total ₹{staying_power_total:,.0f} exceeds non-panic clients' "
        f"current holdings value ₹{float(current_mv):,.0f} — per-window double-count regression"
    )


def test_staying_power_zero_for_panic_clients():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute("select client_id from wealth.client_behaviour where panic_share >= 0.10 limit 1")
    (cid,) = cur.fetchone()
    got = next(r["staying_power_rs"] for r in rows if r["client_id"] == cid)
    assert got == 0
