"""Shared home for the capability-app data layer: JSON-embed hygiene helpers
(moved verbatim from build_capability_app.py, which this package replaces)
plus the top-level `fetch_book(conn)` orchestrator.

Rule #0: every number this package produces traces to a live query against
wealth.*/atlas_foundation.* run inside fetch_book() at build time — nothing
here is a fixture, mock, or invented default.
"""

from __future__ import annotations

import math
import re
import statistics

_XIRR_RE = re.compile(r"(?i)\bXIRR\b")


def _f(x):
    """-> float rounded, or None (never NaN/Inf — strict-JSON safe)."""
    if x is None:
        return None
    v = float(x)
    if not math.isfinite(v):
        return None
    return round(v, 4)


def lcr_py(n: float) -> str:
    """₹ in L/cr, en-IN style (Python mirror of the client-side `lcr()` in
    assets/charts.js — used for build-time verdict/story text)."""
    a = abs(n)
    if a >= 1e7:
        return f"₹{n / 1e7:.2f} cr"
    if a >= 1e5:
        return f"₹{n / 1e5:.2f} L"
    return f"₹{round(n):,}"


def _degarble(s):
    """Strip literal 'XIRR' out of raw DB text (client_flags.evidence,
    client_scorecard.attention_reasons) before embedding, so the banned-word
    gate doesn't trip on data that already says 'XIRR' in the database."""
    return None if s is None else _XIRR_RE.sub("yearly growth", s)


def _hist(values, n_bins=10):
    """Equal-width histogram over the REAL observed min/max + median. Honest
    binning: no fabricated category thresholds, stdlib only."""
    vals = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not vals:
        return {"edges": [], "counts": [], "median": None, "n": 0}
    lo, hi = vals[0], vals[-1]
    if lo == hi:
        return {"edges": [lo, hi], "counts": [len(vals)], "median": lo, "n": len(vals)}
    width = (hi - lo) / n_bins
    counts = [0] * n_bins
    for v in vals:
        counts[min(int((v - lo) / width), n_bins - 1)] += 1
    edges = [round(lo + i * width, 2) for i in range(n_bins + 1)]
    return {
        "edges": edges,
        "counts": counts,
        "median": round(statistics.median(vals), 2),
        "n": len(vals),
    }


def client_names(conn) -> dict[int, str]:
    """client_id -> full_name, for threading a display name onto any
    per-client sample row (render layer needs both id and name to link)."""
    cur = conn.cursor()
    cur.execute("select client_id, full_name from wealth.clients")
    return dict(cur.fetchall())


def fetch_book(conn) -> dict:
    """Top-level orchestrator: runs every capability_app data function against
    a live connection and returns the merged dict the render layer reads.

    Task 1 wired the Holdings-side Q1/Q2/Q3/Q6 functions + the (partial)
    client-index rollup. Task 2 adds the remaining Holdings exhibits (Q4/Q5/
    Q7), the Behaviour-side B1-B5, the client_index chronic-laggard/
    fees-above-median annotation pass, and the per-client Client-360 rollups.
    """
    from . import (
        data_behaviour,
        data_client360_behaviour,
        data_holdings,
        data_holdings_fees,
        data_holdings_overlap,
    )

    data: dict = {}
    data["q1"] = data_holdings.q1_ownership(conn)
    data["q2"] = data_holdings.q2_label_check(conn)
    data["q3"] = data_holdings_overlap.q3_overlap(conn)
    data["q4"] = data_holdings_fees.q4_fees(conn)
    data["q5"] = data_holdings_fees.q5_fund_performance(conn)
    data["q6"] = data_holdings_overlap.q6_bloat_check()
    data["q7"] = data_holdings_fees.q7_cut_list(conn)
    data["b1"] = data_behaviour.b1_advice_vs_index(conn)
    data["b2"] = data_behaviour.b2_behaviour_gap(conn)
    data["b3"] = data_behaviour.b3_panic_pattern(conn)
    data["b4"] = data_behaviour.b4_advice_switches(conn)
    data["b5"] = data_behaviour.b5_what_if_machine(conn)

    client_index = data_holdings_overlap.client_index_rows(conn)
    client_index = data_behaviour.annotate_client_index(conn, client_index)
    data["client_index"] = data_behaviour.annotate_behaviour_flags(conn, client_index)
    data["client360"] = data_client360_behaviour.client_360_all(conn)

    with conn.cursor() as cur:
        cur.execute("select max(as_on_date) from wealth.client_reports")
        (asof,) = cur.fetchone()
    data["asof"] = asof.isoformat() if asof else None

    # Behaviour page's frame line quotes a transaction count/year-span — both
    # must trace to a live query (Rule #0), not be memorized/hardcoded.
    with conn.cursor() as cur:
        cur.execute("select count(*), min(txn_date), max(txn_date) from wealth.transactions")
        n_txns, txn_min, txn_max = cur.fetchone()
    data["n_transactions"] = n_txns
    data["txn_years"] = (txn_max.year - txn_min.year) if (txn_min and txn_max) else None
    return data
