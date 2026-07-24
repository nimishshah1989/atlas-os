"""Real-data tests for the fund-performance engine (Prompt 5).

Rule #0: no fixtures. Every assertion runs against the live
atlas_foundation.* / wealth.* tables via compute_all(), asserting on
relationships in the real computed output — never magic numbers.
"""

import math
import sys

sys.path.insert(0, "scripts/wealth")

from build_fund_performance import compute_all
from engine_common import connect

NUMERIC_KEYS = (
    "roll_3y_pct",
    "roll_5y_pct",
    "dn_capture_pct",
    "best_year_stripped_pct",
    "full_period_pct",
    "beat_count",
    "windows",
)

_CACHE = None


def _rows():
    """compute_all() once (it loads 2.4M NAV rows) and reuse across tests."""
    global _CACHE
    if _CACHE is None:
        conn = connect()
        _CACHE = (conn, compute_all(conn))
    return _CACHE


def test_one_row_per_held_equity_fund():
    conn, rows = _rows()
    cur = conn.cursor()
    cur.execute(
        "select count(distinct s.scheme_id) from wealth.schemes s "
        "join wealth.holdings h using(scheme_id) where s.asset_class = 'Equity'"
    )
    assert len(rows) == cur.fetchone()[0]
    ids = [r["scheme_id"] for r in rows]
    assert len(ids) == len(set(ids)), "scheme_id primary key must be unique"


def test_no_nan_or_inf_in_any_numeric_column():
    _, rows = _rows()
    for r in rows:
        for k in NUMERIC_KEYS:
            v = r[k]
            assert v is None or (isinstance(v, (int, float)) and math.isfinite(v)), (
                f"scheme {r['scheme_id']}: {k}={v!r} is not None/finite"
            )


def test_known_long_largecap_is_scored():
    """A held large-cap fund with >8y of NAV must be fully scored: positive
    3y/5y CAGR (Indian large-cap over the last half-decade is strongly up) and
    a computed downside-capture (it lived through the 2008 + 2020 crashes)."""
    conn, rows = _rows()
    by = {r["scheme_id"]: r for r in rows}
    cur = conn.cursor()
    cur.execute(
        """select s.scheme_id from wealth.schemes s join wealth.holdings h using(scheme_id)
           where s.asset_class = 'Equity' and s.mstar_id is not null
             and s.display_name ilike '%large cap%' and s.display_name not ilike '%mid%'
             and (select min(nav_date) from atlas_foundation.de_mf_nav_daily n
                  where n.mstar_id = s.mstar_id and n.nav > 0)
                 <= current_date - interval '8 years'
           order by s.scheme_id limit 1"""
    )
    sid = cur.fetchone()[0]
    r = by[sid]
    assert r["verdict"] == "scored", r
    assert r["roll_3y_pct"] is not None and r["roll_3y_pct"] > 0
    assert r["roll_5y_pct"] is not None and r["roll_5y_pct"] > 0
    assert r["dn_capture_pct"] is not None
    assert r["full_period_pct"] is not None


def test_recent_fund_is_insufficient_history():
    """A held equity fund whose earliest NAV is < 5y old cannot state a 5y
    number: verdict='insufficient_history', roll_5y_pct NULL."""
    conn, rows = _rows()
    by = {r["scheme_id"]: r for r in rows}
    cur = conn.cursor()
    cur.execute(
        """select s.scheme_id from wealth.schemes s join wealth.holdings h using(scheme_id)
           where s.asset_class = 'Equity' and s.mstar_id is not null
             and (select min(nav_date) from atlas_foundation.de_mf_nav_daily n
                  where n.mstar_id = s.mstar_id and n.nav > 0)
                 > current_date - interval '5 years'
           order by s.scheme_id limit 1"""
    )
    sid = cur.fetchone()[0]
    r = by[sid]
    assert r["verdict"] == "insufficient_history", r
    assert r["roll_5y_pct"] is None


def test_best_year_stripped_below_full_period():
    """The 'one lucky year' test: for a fund that made money over its life,
    removing its single best rolling-12m window can only lower the annualised
    return. Restrict to full_period > 0 (for funds that LOST money over their
    life the strip-a-year arithmetic legitimately inverts)."""
    _, rows = _rows()
    sampled = [
        r
        for r in rows
        if r["best_year_stripped_pct"] is not None
        and r["full_period_pct"] is not None
        and r["full_period_pct"] > 0
    ]
    assert len(sampled) > 50, "expected many long positive-return funds in the book"
    for r in sampled:
        assert r["best_year_stripped_pct"] <= r["full_period_pct"] + 1e-9, (
            f"scheme {r['scheme_id']}: stripped {r['best_year_stripped_pct']} "
            f"> full {r['full_period_pct']}"
        )


def test_dn_capture_positive_and_plausible():
    """Downside capture is a ratio of two declines → strictly positive; equity
    funds roughly track the market in a crash → the cohort mean lands in a sane
    band (they capture most, not a multiple, of market downside)."""
    _, rows = _rows()
    vals = [r["dn_capture_pct"] for r in rows if r["dn_capture_pct"] is not None]
    assert len(vals) > 50
    assert all(v > 0 for v in vals), "a decline-over-decline ratio cannot be negative"
    mean = sum(vals) / len(vals)
    assert 40 < mean < 160, f"cohort mean dn_capture {mean:.1f}% implausible for equity funds"


def test_benchmark_legs_present_and_nulls_are_explained():
    _, rows = _rows()
    assert any(r["beat_count"] is not None and r["windows"] and r["windows"] > 0 for r in rows), (
        "funds with a mappable benchmark must have beat_count over real windows"
    )
    for r in rows:
        if r["beat_count"] is None:
            assert r["benchmark_note"], (
                f"scheme {r['scheme_id']}: null benchmark legs but no explanatory note"
            )
