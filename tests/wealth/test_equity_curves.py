"""Equity-curve engine (Task 4) — asserts on REAL wealth.client_curves /
wealth.client_curve_events rows (Rule #0). No fixtures: every client and
number here comes from the engine's own live output, cross-checked against
independent SQL over wealth.transactions / wealth.holdings / wealth.schemes /
wealth.client_behaviour and the same behaviour_fingerprints.drawdown_windows
used across the rest of the book.
Run: .venv/bin/python -m pytest tests/wealth/test_equity_curves.py -v
"""

import os
import sys

import psycopg2
import pytest

sys.path.insert(0, "scripts/wealth")

from behaviour_fingerprints import drawdown_windows
from engine_common import BENCH_ID, nav_series

DSN = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")


def _conn():
    return psycopg2.connect(DSN)


def test_no_negative_value_rs_anywhere():
    cur = _conn().cursor()
    cur.execute("select count(*) from wealth.client_curves where value_rs < 0")
    assert cur.fetchone()[0] == 0


def test_every_event_date_matches_a_real_transaction_for_that_client():
    cur = _conn().cursor()
    cur.execute(
        """select count(*) from wealth.client_curve_events e
           where not exists (
             select 1 from wealth.transactions t
             where t.client_id = e.client_id and t.txn_date = e.event_date
           )"""
    )
    bad = cur.fetchone()[0]
    assert bad == 0, f"{bad} event(s) have no matching real transaction for that client"
    cur.execute("select count(*) from wealth.client_curve_events")
    assert cur.fetchone()[0] > 0, "engine produced zero story events"


def test_event_kinds_are_from_the_allowed_set():
    cur = _conn().cursor()
    cur.execute("select distinct kind from wealth.client_curve_events")
    kinds = {r[0] for r in cur.fetchall()}
    assert kinds and kinds <= {"panic_sell", "sip_stop", "big_inflow", "big_outflow"}


def test_sampled_client_final_point_matches_holdings_mv_times_coverage():
    cur = _conn().cursor()
    # highest-current-MV client so the check is meaningful (not a near-zero book)
    cur.execute(
        """select h.client_id, sum(h.market_value)
           from wealth.holdings h
           where h.market_value > 0
           group by h.client_id
           order by sum(h.market_value) desc
           limit 1"""
    )
    cid, holdings_mv = cur.fetchone()
    holdings_mv = float(holdings_mv)

    cur.execute(
        "select month, value_rs, coverage_pct from wealth.client_curves "
        "where client_id = %s order by month desc limit 1",
        (cid,),
    )
    row = cur.fetchone()
    assert row is not None, f"client {cid} has no curve rows"
    _month, value_rs, coverage_pct = row
    assert coverage_pct is not None, f"client {cid} has real holdings but null coverage_pct"

    value_rs = float(value_rs)
    expected = holdings_mv * float(coverage_pct) / 100.0
    # holdings snapshot (client_reports.as_on_date) trails "now" by ~1-2 weeks, so
    # allow generous NAV-drift tolerance rather than a tight same-day match.
    tol = max(expected, value_rs) * 0.10
    assert abs(value_rs - expected) <= tol, (
        f"client {cid}: final value_rs={value_rs:,.0f} vs holdings_mv*coverage="
        f"{expected:,.0f} (coverage {coverage_pct}%), "
        f"diff {abs(value_rs - expected):,.0f} > tol {tol:,.0f}"
    )


EXOTIC_UNIT_TYPES = ("pledge", "dtp_in", "dtp_out", "merger_in", "consolidation_in", "transfer_in")


def test_sampled_exotic_type_client_final_point_matches_holdings_mv_times_coverage():
    """Same check as above, but for a client whose ledger includes an atypical
    unit-moving txn_type (not one of the special-cased buy/sell/redemption
    types) — this exercises the generic is_debit-driven reconstruction that
    NO_UNIT_EFFECT doesn't special-case."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """select client_id, count(*) from wealth.transactions
           where txn_type in %s
           group by client_id order by count(*) desc limit 1""",
        (EXOTIC_UNIT_TYPES,),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        pytest.skip(f"no client has any of {EXOTIC_UNIT_TYPES} transactions")
    cid, _n = row

    cur.execute(
        """select sum(h.market_value) from wealth.holdings h
           where h.client_id = %s and h.market_value > 0
           group by h.client_id""",
        (cid,),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        pytest.skip(f"exotic-type client {cid} has no positive holdings to compare against")
    (holdings_mv,) = row
    holdings_mv = float(holdings_mv)

    cur.execute(
        "select month, value_rs, coverage_pct from wealth.client_curves "
        "where client_id = %s order by month desc limit 1",
        (cid,),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None, f"exotic-type client {cid} has no curve rows"
    _month, value_rs, coverage_pct = row
    assert coverage_pct is not None, f"client {cid} has real holdings but null coverage_pct"

    value_rs = float(value_rs)
    expected = holdings_mv * float(coverage_pct) / 100.0
    tol = max(expected, value_rs) * 0.10
    assert abs(value_rs - expected) <= tol, (
        f"exotic-type client {cid}: final value_rs={value_rs:,.0f} vs holdings_mv*coverage="
        f"{expected:,.0f} (coverage {coverage_pct}%), "
        f"diff {abs(value_rs - expected):,.0f} > tol {tol:,.0f}"
    )


def test_coverage_pct_matches_independent_sql_and_is_stable_across_months():
    cur = _conn().cursor()
    cur.execute(
        "select client_id from wealth.client_curves where coverage_pct is not null "
        "group by client_id order by count(*) desc limit 1"
    )
    (cid,) = cur.fetchone()
    cur.execute(
        """select coalesce(sum(h.market_value) filter (
                    where s.mstar_id is not null and s.has_nav_series), 0)
                  / nullif(sum(h.market_value), 0) * 100
           from wealth.holdings h join wealth.schemes s using (scheme_id)
           where h.client_id = %s""",
        (cid,),
    )
    (expected,) = cur.fetchone()
    cur.execute(
        "select distinct coverage_pct from wealth.client_curves where client_id = %s", (cid,)
    )
    rows = cur.fetchall()
    assert len(rows) == 1, f"client {cid} has varying coverage_pct across months: {rows}"
    (stored,) = rows[0]
    assert abs(float(stored) - float(expected)) < 0.5, (cid, stored, expected)


def test_known_panic_seller_has_panic_sell_event_in_a_drawdown_window():
    cur = _conn().cursor()
    cur.execute(
        "select client_id from wealth.client_behaviour "
        "order by panic_loss_out_rs desc nulls last limit 1"
    )
    (cid,) = cur.fetchone()
    cur.execute(
        "select event_date from wealth.client_curve_events "
        "where client_id = %s and kind = 'panic_sell'",
        (cid,),
    )
    dates = [r[0] for r in cur.fetchall()]
    assert dates, f"top panic-loss client {cid} has no panic_sell event"

    conn = _conn()
    windows = drawdown_windows(nav_series(conn, BENCH_ID))
    import pandas as pd

    assert any(any(a <= pd.Timestamp(d) <= b for a, b in windows) for d in dates), (
        f"client {cid}'s panic_sell dates {dates} fall outside every drawdown window"
    )
