"""Q3 (overlap), Q6 (bloat empty-state), and the client-index rollup — split
out of data_holdings.py to stay under the 600-LOC file limit. Same contract
as data_holdings.py: every function takes a live `conn` and returns real
query output, no fixtures.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from build_overlap import latest_fund_weights, pairwise_overlap

from .data import _f, lcr_py

# Mirrors build_cut_list.py's pre-existing hardcoded `overlap_pct > 50` literal
# (its "redundant" fund-pair cutoff) — constraint 5 requires that cutoff live in
# atlas_foundation.atlas_thresholds, not a second Python literal. Seeded once,
# idempotently, the same insert-if-absent idiom build_call_lists.load_armed_floor
# already uses (atlas_thresholds has no unique constraint on threshold_key).
OVERLAP_DUPLICATE_KEY = "wealth_overlap_duplicate_pct"
OVERLAP_DUPLICATE_DEFAULT = 50.0


def _seed_overlap_threshold(conn) -> float:
    """Idempotent bootstrap + read-back of OVERLAP_DUPLICATE_KEY. Safe to call
    from multiple exhibit functions / repeated test runs — the WHERE NOT EXISTS
    guard makes the insert a no-op after the first real run."""
    cur = conn.cursor()
    cur.execute(
        """insert into atlas_foundation.atlas_thresholds
             (threshold_key, threshold_value, category, description, units,
              default_value, is_active, created_at, last_modified_by, last_modified_at)
           select %(k)s, %(v)s, 'wealth',
                  'Overlap pct above which a held fund pair counts as a duplicate '
                  'holding for the capability-app Overlap Trap exhibit (Q3/Q7). '
                  'Mirrors build_cut_list.py''s pre-existing hardcoded ''overlap_pct '
                  '> 50'' literal (its redundant-fund-pair cutoff) -- new row, flag '
                  'for FM sign-off per CLAUDE.md constraint 5.',
                  'pct', %(v)s, true, now(), 'system', now()
           where not exists (
             select 1 from atlas_foundation.atlas_thresholds where threshold_key = %(k)s)""",
        {"k": OVERLAP_DUPLICATE_KEY, "v": OVERLAP_DUPLICATE_DEFAULT},
    )
    conn.commit()
    cur.execute(
        "select threshold_value from atlas_foundation.atlas_thresholds where threshold_key = %s",
        (OVERLAP_DUPLICATE_KEY,),
    )
    return float(cur.fetchone()[0])


def q3_overlap(conn) -> dict:
    """How much duplicated? Book KPI tiles over wealth.client_fund_overlap
    (all stored pairs) + a top-15x15 book-wide fund overlap/stock-weight
    sample via build_overlap.latest_fund_weights/pairwise_overlap."""
    threshold = _seed_overlap_threshold(conn)
    cur = conn.cursor()

    cur.execute("select overlap_pct::float from wealth.client_fund_overlap")
    all_pct = [r[0] for r in cur.fetchall()]
    median_overlap = round(statistics.median(all_pct), 2) if all_pct else None

    cur.execute(
        """with hv as (
             select client_id, scheme_id, sum(market_value)::float mv
             from wealth.holdings where market_value > 0 group by 1, 2)
           select o.client_id, o.scheme_a, o.scheme_b, o.overlap_pct::float, va.mv, vb.mv
           from wealth.client_fund_overlap o
           join hv va on va.client_id = o.client_id and va.scheme_id = o.scheme_a
           join hv vb on vb.client_id = o.client_id and vb.scheme_id = o.scheme_b
           where o.overlap_pct > %s
           order by o.overlap_pct desc""",
        (threshold,),
    )
    dup_pairs = cur.fetchall()
    pairs_above = len(dup_pairs)
    rupee_duplicated = sum(pct / 100.0 * min(va, vb) for _c, _a, _b, pct, va, vb in dup_pairs)

    cur.execute(
        """select s.scheme_id, s.display_name, s.mstar_id, sum(h.market_value)::float
           from wealth.holdings h join wealth.schemes s using (scheme_id)
           where h.market_value > 0 and s.mstar_id is not null
           group by 1, 2, 3"""
    )
    fund_rows = cur.fetchall()
    fw = latest_fund_weights(conn)
    eligible = [(sid, name, mid, val) for sid, name, mid, val in fund_rows if mid in fw]
    top15 = sorted(eligible, key=lambda r: -r[3])[:15]

    pairwise = []
    for i in range(len(top15)):
        for j in range(i + 1, len(top15)):
            sid_a, _na, mid_a, _va = top15[i]
            sid_b, _nb, mid_b, _vb = top15[j]
            pairwise.append(
                {
                    "scheme_a": sid_a,
                    "scheme_b": sid_b,
                    "overlap_pct": pairwise_overlap(fw[mid_a], fw[mid_b]),
                }
            )

    # "cluster" evidence = stocks actually SHARED by >=2 of the top-15 funds (a
    # stock only one fund holds, however heavily, proves no overlap by itself).
    stock_totals: dict[str, float] = defaultdict(float)
    stock_holders: dict[str, int] = defaultdict(int)
    stock_names: dict[str, str] = {}
    for _sid, _name, mid, _val in top15:
        for isin, (nm, w) in fw[mid].items():
            stock_totals[isin] += w
            stock_holders[isin] += 1
            stock_names[isin] = nm
    shared = [isin for isin in stock_totals if stock_holders[isin] >= 2]
    top_stocks = sorted(shared, key=lambda i: -stock_totals[i])[:20]
    stock_matrix = [
        {
            "isin": isin,
            "name": stock_names[isin],
            "n_funds_holding": stock_holders[isin],
            "total_weight_pct": _f(stock_totals[isin]),
            "weights": {
                str(sid): _f(fw[mid].get(isin, (None, 0.0))[1]) for sid, _n, mid, _v in top15
            },
        }
        for isin in top_stocks
    ]

    verdict = (
        f"{pairs_above} fund pairs overlap more than {int(threshold)}%; "
        f"{lcr_py(rupee_duplicated)} sits in effectively duplicated exposure."
    )

    sample_rows = [
        {"client_id": cid, "scheme_a": a, "scheme_b": b, "overlap_pct": _f(pct)}
        for cid, a, b, pct, _va, _vb in dup_pairs[:20]
    ]

    return {
        "threshold_pct": threshold,
        "median_overlap_pct": median_overlap,
        "pairs_above_threshold": pairs_above,
        "rupee_duplicated_rs": _f(rupee_duplicated),
        "top15_funds": [
            {"scheme_id": sid, "fund": name, "value_cr": _f(val / 1e7)}
            for sid, name, _mid, val in top15
        ],
        "top15_pairwise": pairwise,
        "top15_stock_matrix": stock_matrix,
        "verdict": verdict,
        "honesty": "estimate",
        "working": {
            "inputs": [
                {"label": "Duplicate-pair threshold (atlas_thresholds)", "value": threshold},
                {"label": "Median overlap among stored pairs", "value": median_overlap},
                {"label": "Pairs above threshold", "value": pairs_above},
                {"label": "Rupees duplicated", "value": _f(rupee_duplicated)},
            ],
            "rule": (
                "wealth.client_fund_overlap only stores pairs with overlap_pct >= 20 "
                "(build_overlap.py's storage cutoff). 'Duplicate pair' = overlap_pct > "
                f"{OVERLAP_DUPLICATE_KEY} (atlas_thresholds, seeded at "
                f"{OVERLAP_DUPLICATE_DEFAULT}). Rupees duplicated per pair = "
                "overlap_pct/100 * min(held value of scheme_a, held value of "
                "scheme_b) for that client, summed over every pair above the "
                "threshold. The top-15x15 fund overlap matrix and per-stock weight "
                "table are book-wide (not per-client): the 15 largest funds by total "
                "held value, scoped to funds with a look-through weight map "
                "(build_overlap.latest_fund_weights), pairwise overlap via "
                "build_overlap.pairwise_overlap (sum of min(weight_a, weight_b) over "
                "shared ISINs). The stock-weight evidence table keeps only ISINs held "
                "by 2+ of the 15 funds (a stock only one fund holds, however heavily, "
                "isn't overlap by itself), ranked by summed weight across the 15."
            ),
            "assumptions": [
                {
                    "text": "'rupees duplicated' treats overlap_pct of the SMALLER "
                    "position as the duplicated money — a heuristic, not a literal "
                    "rupee-for-rupee redundancy count",
                    "bias": "estimate — approximates duplication rather than tracing "
                    "each duplicated rupee to a specific stock",
                },
                {
                    "text": "the stock-weight evidence table samples only the 15 "
                    "largest book-wide funds, not every held fund pair",
                    "bias": "estimate — a smaller fund pair could overlap just as "
                    "heavily but isn't in this sample",
                },
            ],
            "steps": [
                {"label": "Stored pairs (overlap_pct >= 20)", "value": len(all_pct)},
                {"label": "Pairs above duplicate threshold", "value": pairs_above},
                {
                    "label": "Sum of overlap_pct/100 * min(value_a, value_b)",
                    "value": _f(rupee_duplicated),
                },
            ],
            "sample_rows": sample_rows,
            "sample_of": pairs_above,
            "honesty": "estimate",
        },
    }


def q6_bloat_check() -> dict:
    """Is anything bloated? Honest empty state: no factsheet/SID feed exists
    anywhere in the pipeline, so manager tenure / AUM growth / turnover ratio
    / mandate changes have no source to compute from. No invented proxy."""
    return {
        "question": (
            "Is anything bloated? (manager tenure, AUM growth, turnover ratio, mandate changes)"
        ),
        "message": (
            "We don't have this data — a factsheet/SID feed would be needed. No "
            "engine in this pipeline ingests manager tenure, AUM growth, portfolio "
            "turnover ratio, or mandate-change history."
        ),
        "working": {
            "inputs": [],
            "rule": "no factsheet/SID feed exists in the pipeline",
            "assumptions": [],
            "steps": [],
            "sample_rows": [],
            "sample_of": 0,
            "honesty": None,
        },
    }


def client_index_rows(conn) -> dict:
    """One row per client (bottom of the Holdings page, shared with Task 4):
    name, value, fund count, off-label/overlap flags, segment. The
    chronic-laggard and fees-above-median flags are added in Task 2 once
    Q4/Q5 land — this rollup returns everything Q1-Q3 can already answer."""
    threshold = _seed_overlap_threshold(conn)
    cur = conn.cursor()

    cur.execute("select client_id, full_name from wealth.clients")
    names = {cid: name for cid, name in cur.fetchall()}

    cur.execute(
        """select client_id, sum(market_value)::float, count(distinct scheme_id)
           from wealth.holdings where market_value > 0 group by 1"""
    )
    base = {cid: (val, n) for cid, val, n in cur.fetchall()}

    cur.execute(
        """select h.client_id, sum(h.market_value)::float
           from wealth.holdings h join wealth.fund_label_check flc using (scheme_id)
           where h.market_value > 0 and flc.verdict = 'mismatch'
           group by 1"""
    )
    off_label = {cid: v for cid, v in cur.fetchall()}

    cur.execute(
        "select distinct client_id from wealth.client_fund_overlap where overlap_pct > %s",
        (threshold,),
    )
    overlap_flag = {r[0] for r in cur.fetchall()}

    cur.execute("select client_id, segment from wealth.client_segments")
    segments = {cid: seg for cid, seg in cur.fetchall()}

    rows = []
    for cid, (value, n_funds) in base.items():
        off = off_label.get(cid, 0.0)
        rows.append(
            {
                "client_id": cid,
                "name": names.get(cid),
                "value_rs": _f(value),
                "fund_count": n_funds,
                "off_label_rs": _f(off),
                "off_label_flag": off > 0,
                "overlap_flag": cid in overlap_flag,
                "segment": segments.get(cid),
            }
        )
    rows.sort(key=lambda r: -(r["value_rs"] or 0.0))
    return {"rows": rows, "n_clients": len(rows)}
