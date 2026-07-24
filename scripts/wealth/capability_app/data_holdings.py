"""Book-level rollups for the Holdings-page exhibits Q1 (ownership) and Q2
(label check). Q3/Q6/client-index live in data_holdings_overlap.py (split to
stay under the 600-LOC file limit); Q4/Q5/Q7 land in data_behaviour.py (Task 2).

Every function takes a live `conn` (engine_common.connect()) and returns a
plain dict: the exhibit's chart-ready rollups plus a `working` object
(constraint 14's universal shape: inputs/rule/assumptions/steps/sample_rows/
sample_of/honesty). No fixtures, no synthetic numbers — every figure here is
computed from wealth.*/atlas_foundation.* at call time.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable

from .data import _f, _hist, lcr_py

# ---------------------------------------------------------------------- Q1 --


def q1_ownership(conn) -> dict:
    """What do you actually own? Book-wide rollup of wealth.holdings x
    wealth.schemes: total value, distinct funds/AMCs, funds-per-client
    distribution, top-10 funds, and a category->AMC->fund treemap."""
    cur = conn.cursor()
    cur.execute("select count(*) from wealth.holdings")
    holdings_table_rows = cur.fetchone()[0]

    cur.execute(
        """select h.client_id, h.scheme_id, s.display_name, s.asset_class,
                  split_part(s.display_name, ' ', 1) as amc, h.market_value::float
           from wealth.holdings h join wealth.schemes s using (scheme_id)
           where h.market_value > 0"""
    )
    rows = cur.fetchall()

    fund_value: dict[int, float] = defaultdict(float)
    fund_meta: dict[int, tuple] = {}
    amc_set: set[str] = set()
    client_funds: dict[int, set] = defaultdict(set)
    treemap: dict[tuple, float] = defaultdict(float)

    for cid, sid, name, category, amc, value in rows:
        fund_value[sid] += value
        fund_meta[sid] = (name, category, amc)
        amc_set.add(amc)
        client_funds[cid].add(sid)
        treemap[(category, amc, name)] += value

    total_value = sum(fund_value.values())
    n_funds = len(fund_value)
    n_amcs = len(amc_set)
    hist = _hist([len(s) for s in client_funds.values()])

    top10 = sorted(fund_value.items(), key=lambda kv: -kv[1])[:10]
    top10_rows = [
        {
            "scheme_id": sid,
            "fund": fund_meta[sid][0],
            "category": fund_meta[sid][1],
            "amc": fund_meta[sid][2],
            "value_cr": _f(v / 1e7),
            "share_pct": _f(v / total_value * 100) if total_value else None,
        }
        for sid, v in top10
    ]
    treemap_rows = [
        {"category": cat, "amc": amc, "fund": name, "value_cr": _f(v / 1e7)}
        for (cat, amc, name), v in sorted(treemap.items(), key=lambda kv: -kv[1])
    ]

    median_funds = hist["median"]
    verdict = f"{lcr_py(total_value)} across {n_funds} funds, {n_amcs} fund houses."
    if median_funds is not None:
        verdict += f" Median client holds {int(median_funds)} funds."

    sample_rows = [
        {
            "client_id": cid,
            "scheme_id": sid,
            "fund": name,
            "category": category,
            "amc": amc,
            "value_rs": _f(value),
        }
        for cid, sid, name, category, amc, value in rows[:20]
    ]

    return {
        "total_value_rs": _f(total_value),
        "n_funds": n_funds,
        "n_amcs": n_amcs,
        "funds_per_client_hist": hist,
        "top10_funds": top10_rows,
        "treemap": treemap_rows,
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Total value held", "value": _f(total_value)},
                {"label": "Distinct funds held", "value": n_funds},
                {"label": "Distinct fund houses (AMCs)", "value": n_amcs},
                {"label": "Median funds per client", "value": median_funds},
            ],
            "rule": (
                "wealth.holdings joined to wealth.schemes on scheme_id, filtered to "
                "market_value > 0; AMC parsed as the first word of the scheme display "
                "name (same convention as cohort_report.py / client_analytics.py); "
                "rolled up category -> AMC -> fund by summed market_value."
            ),
            "assumptions": [
                {
                    "text": "AMC is the first word of the scheme display name, not a "
                    "separate fund-house master field",
                    "bias": "a few multi-word AMC names may render oddly as a label — "
                    "no effect on the underlying rupee totals",
                }
            ],
            "steps": [
                {"label": "Sum market_value over held rows", "value": _f(total_value)},
                {"label": "Count distinct scheme_id", "value": n_funds},
                {"label": "Count distinct AMC", "value": n_amcs},
                {"label": "Median of per-client distinct-fund counts", "value": median_funds},
            ],
            "sample_rows": sample_rows,
            "sample_of": len(rows),
            "honesty": "exact",
        },
        "_holdings_table_rows": holdings_table_rows,
    }


# ---------------------------------------------------------------------- Q2 --

# Decomposes build_label_check.py's CATEGORY_RULES boolean lambdas into one
# numeric threshold per composition leg, so the exhibit can chart "actual %
# vs mandate %" per category. Not imported directly: CATEGORY_RULES pairs a
# compiled regex + an opaque pass/fail lambda, it doesn't expose per-leg
# threshold values — these formulas are transcribed verbatim from it.
MANDATE_LEGS: dict[str, list[tuple[str, Callable[[float], float]]]] = {
    "Large Cap": [("large_pct", lambda e: 80.0 * e / 100.0)],
    "Mid Cap": [("mid_pct", lambda e: 65.0 * e / 100.0)],
    "Small Cap": [("small_pct", lambda e: 65.0 * e / 100.0)],
    "Multi Cap": [
        ("large_pct", lambda e: 25.0),
        ("mid_pct", lambda e: 25.0),
        ("small_pct", lambda e: 25.0),
    ],
    "Large & Mid Cap": [("large_pct", lambda e: 35.0), ("mid_pct", lambda e: 35.0)],
    "Flexi Cap": [("equity_pct", lambda e: 65.0)],
}


def q2_label_check(conn) -> dict:
    """Does the label match the contents? wealth.fund_label_check joined to
    held value, per-category actual-vs-mandate bars, and an offenders table."""
    cur = conn.cursor()
    cur.execute(
        """select h.client_id, h.scheme_id, s.display_name, flc.category, flc.verdict,
                  flc.large_pct::float, flc.mid_pct::float, flc.small_pct::float,
                  flc.equity_pct::float, flc.detail, flc.mstar_id, h.market_value::float
           from wealth.holdings h
           join wealth.schemes s using (scheme_id)
           join wealth.fund_label_check flc using (scheme_id)
           where h.market_value > 0"""
    )
    rows = cur.fetchall()

    fund_value: dict[int, float] = defaultdict(float)
    fund_meta: dict[int, dict] = {}
    for _cid, sid, name, category, verdict, l, m, s_, e, detail, mstar, value in rows:
        fund_value[sid] += value
        fund_meta[sid] = {
            "fund": name,
            "category": category,
            "verdict": verdict,
            "large_pct": l,
            "mid_pct": m,
            "small_pct": s_,
            "equity_pct": e,
            "detail": detail,
            "mstar_id": mstar,
        }

    mismatch_sids = {sid for sid, m in fund_meta.items() if m["verdict"] == "mismatch"}
    mismatch_value = sum(fund_value[sid] for sid in mismatch_sids)

    mismatch_mstars = sorted(
        {fund_meta[sid]["mstar_id"] for sid in mismatch_sids if fund_meta[sid]["mstar_id"]}
    )
    as_of_min = as_of_max = None
    if mismatch_mstars:
        cur.execute(
            """select min(d), max(d) from (
                 select mstar_id, max(as_of_date) d from atlas_foundation.de_mf_holdings
                 where mstar_id = any(%s) group by 1) t""",
            (mismatch_mstars,),
        )
        as_of_min, as_of_max = cur.fetchone()
    month_label = as_of_max.strftime("%b %Y") if as_of_max else "unknown"

    by_category: dict[str, list] = defaultdict(list)
    for meta in fund_meta.values():
        by_category[meta["category"]].append(meta)

    category_bars = []
    for cat, legs in MANDATE_LEGS.items():
        members = by_category.get(cat, [])
        if not members:
            continue
        leg_rows = []
        for metric, threshold_fn in legs:
            actuals = [m[metric] for m in members if m[metric] is not None]
            if not actuals:
                continue
            mandates = [threshold_fn(m["equity_pct"] or 0.0) for m in members]
            leg_rows.append(
                {
                    "metric": metric,
                    "actual_pct": _f(statistics.mean(actuals)),
                    "mandate_pct": _f(statistics.mean(mandates)),
                }
            )
        category_bars.append(
            {
                "category": cat,
                "n_funds": len(members),
                "n_mismatch": sum(1 for m in members if m["verdict"] == "mismatch"),
                "legs": leg_rows,
            }
        )

    offenders = []
    for sid in mismatch_sids:
        meta = fund_meta[sid]
        shortfall = 0.0
        for metric, threshold_fn in MANDATE_LEGS.get(meta["category"], []):
            actual = meta[metric]
            if actual is None:
                continue
            mandate = threshold_fn(meta["equity_pct"] or 0.0)
            shortfall = max(shortfall, mandate - actual)
        offenders.append(
            {
                "scheme_id": sid,
                "fund": meta["fund"],
                "category": meta["category"],
                "shortfall_pct": _f(shortfall),
                "value_rs": _f(fund_value[sid]),
                "detail": meta["detail"],
            }
        )
    offenders.sort(key=lambda r: -(r["shortfall_pct"] or 0.0))

    verdict = (
        f"{lcr_py(mismatch_value)} sits in funds whose name doesn't match their "
        f"contents (as of {month_label})."
    )

    sample_rows = [
        {
            "client_id": cid,
            "scheme_id": sid,
            "fund": name,
            "category": category,
            "verdict": verdict_,
            "value_rs": _f(value),
        }
        for cid, sid, name, category, verdict_, *_rest, value in rows[:20]
    ]

    return {
        "mismatch_value_rs": _f(mismatch_value),
        "n_mismatch_funds": len(mismatch_sids),
        "as_of_month": month_label,
        "as_of_min": as_of_min.isoformat() if as_of_min else None,
        "as_of_max": as_of_max.isoformat() if as_of_max else None,
        "category_bars": category_bars,
        "offenders": offenders[:20],
        "verdict": verdict,
        "honesty": "exact",
        "working": {
            "inputs": [
                {"label": "Value in mismatch funds", "value": _f(mismatch_value)},
                {"label": "Mismatch funds held", "value": len(mismatch_sids)},
                {"label": "Disclosure month (latest of the mismatch set)", "value": month_label},
            ],
            "rule": (
                "wealth.fund_label_check.verdict='mismatch' (SEBI large/mid/small "
                "cap-mandate vs the fund's actual disclosed composition, per "
                "build_label_check.py's CATEGORY_RULES) joined to wealth.holdings for "
                "client-held value; 'no_data' funds and category='Other' (no cap "
                "mandate applies, e.g. a sectoral fund) never count as mismatches. "
                "Disclosure date re-derived from atlas_foundation.de_mf_holdings "
                "max(as_of_date) per mstar_id since fund_label_check itself doesn't "
                "persist the date it used."
            ),
            "assumptions": [
                {
                    "text": "category-bar 'mandate' values decompose "
                    "build_label_check's compound pass/fail rule (e.g. Large & Mid "
                    "needs BOTH legs >=35%) into one number per leg, averaged across "
                    "held funds in that category",
                    "bias": "a fund can fail on only one leg — the per-leg average "
                    "can understate how close or far an individual fund sits from its "
                    "own mandate",
                },
                {
                    "text": "the headline 'as of <month>' uses the MOST RECENT "
                    "disclosure among held mismatch funds' mstar_ids",
                    "bias": "some mismatch funds' disclosures are older than the "
                    "headline month — see as_of_min for the true range",
                },
            ],
            "steps": [
                {"label": "Join holdings to fund_label_check", "value": len(rows)},
                {"label": "Filter verdict = mismatch", "value": len(mismatch_sids)},
                {"label": "Sum held value of mismatch funds", "value": _f(mismatch_value)},
            ],
            "sample_rows": sample_rows,
            "sample_of": len(rows),
            "honesty": "exact",
        },
    }
