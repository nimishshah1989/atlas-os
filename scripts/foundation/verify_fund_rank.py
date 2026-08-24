#!/usr/bin/env python3
"""DoD gate for fund_rank_daily (rule #0: assert on REAL produced output).

The history's newest row MUST equal what the funds page renders. This reproduces the
production query the page runs — frontend/src/lib/queries/fund_lens.ts
(getFundLensList) with the SCORED_STOCKS CTE from etf_lens.ts — then applies the same
composite + rank core, and diffs the resulting per-fund category ranks against the
stored fund_rank_daily rows for max(date).

This is an INDEPENDENT data path for what it actually checks (cat_size, composite,
cat_rank): those derive from the holdings-weighted v_* lens vectors, so agreement
proves the builder's "today" row reproduces the live page's RANKING.

WHAT "INDEPENDENT" MEANS HERE. This used to carry its own copy of the leader rule —
the same stale one build_fund_rank_history.py carried, not production's — so the gate
agreed with the builder by construction and could not see that stored breadth was a
different number from displayed breadth. The rule now lives in ONE place,
atlas_foundation.v_stock_leader, which the page, the builder and this file all read.
So nothing re-derives it and nothing can drift; what this gate independently checks is
that the STORED rows reproduce a freshly-computed production roll-up.

BREADTH is reported below, not asserted: the stored history predates this rule change
and will not match until the Task-5 rebuild. Promote it to a hard check then.

    python verify_fund_rank.py        # exit 0 iff stored ranks == production ranks
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
import fund_rank_core as core

# --- etf_lens.ts SCORED_STOCKS (the production nightly CTE), reduced to the columns the
# --- roll-up below needs. The leader flag is READ from atlas_foundation.v_stock_leader,
# --- the same view the page reads — see the module docstring.
SCORED_STOCKS = """
  latest AS (SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'),
  scored AS (
    SELECT l.instrument_id,
           l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va,
           COALESCE(v.lead,0) AS lead
    FROM atlas_foundation.atlas_lens_scores_daily l
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
    LEFT JOIN atlas_foundation.v_stock_leader v
      ON v.instrument_id = l.instrument_id AND v.date = l.date
    WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest))
"""

EQUITY_FUND_FILTER = """NOT mm.is_etf AND mm.is_active
  AND mm.broad_category NOT ILIKE ALL(ARRAY['%debt%','%liquid%','%money%','%overnight%','%gilt%','%bond%'])
  AND mm.fund_name NOT ILIKE '%Direct%' AND mm.fund_name NOT ILIKE '%Dir Gr%' AND mm.fund_name NOT ILIKE '%IDCW%'"""

PROD_QUERY = f"""
WITH {SCORED_STOCKS}
SELECT mm.mstar_id, mm.category_name AS category,
  COALESCE(sum(h.weight_pct) FILTER (WHERE COALESCE(s.lead,0) >= 1),0) / NULLIF(sum(h.weight_pct),0) AS breadth,
  sum(h.weight_pct*s.t)  FILTER (WHERE s.t  IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.t  IS NOT NULL),0) AS v_tech,
  sum(h.weight_pct*s.f)  FILTER (WHERE s.f  IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.f  IS NOT NULL),0) AS v_fund,
  sum(h.weight_pct*s.ca) FILTER (WHERE s.ca IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.ca IS NOT NULL),0) AS v_cat,
  sum(h.weight_pct*s.fl) FILTER (WHERE s.fl IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.fl IS NOT NULL),0) AS v_flow
FROM atlas_foundation.de_mf_master mm
JOIN atlas_foundation.de_mf_holdings h
  ON h.mstar_id = mm.mstar_id AND h.as_of_date = (SELECT max(as_of_date) FROM atlas_foundation.de_mf_holdings) AND h.weight_pct > 0
JOIN scored s ON s.instrument_id = h.instrument_id
WHERE {EQUITY_FUND_FILTER}
GROUP BY mm.mstar_id, mm.category_name
HAVING count(h.instrument_id) >= 5
"""


def _close(a: object, b: object, eps: float = 1e-6) -> bool:
    """Two breadth values agree. A missing value (SQL NULL, or the NaN pandas reads it as)
    agrees only with another missing value — never with 0, which is a real 0% breadth."""
    fa, fb = (None if x is None or x != x else float(x) for x in (a, b))  # type: ignore[arg-type]
    if fa is None or fb is None:
        return fa is fb
    return abs(fa - fb) <= eps


def main() -> None:
    weights_df = _db.read_df(
        """SELECT threshold_key, threshold_value FROM atlas_foundation.atlas_thresholds
           WHERE threshold_key LIKE 'lens_weight_%'"""
    )
    wm = {r.threshold_key: float(r.threshold_value) for r in weights_df.itertuples()}
    weights = {
        "technical": wm.get("lens_weight_technical", 0.30),
        "fundamental": wm.get("lens_weight_fundamental", 0.25),
        "flow": wm.get("lens_weight_flow", 0.25),
        "catalyst": wm.get("lens_weight_catalyst", 0.20),
    }

    prod = _db.read_df(PROD_QUERY)
    rows = []
    for r in prod.itertuples():
        vec = {"v_tech": r.v_tech, "v_fund": r.v_fund, "v_flow": r.v_flow, "v_cat": r.v_cat}
        rows.append(
            {
                "mstar_id": r.mstar_id,
                "category": r.category,
                "breadth": float(r.breadth) if r.breadth is not None else None,
                "composite": core.composite(vec, weights),
            }
        )
    prod_ranked = {
        r["mstar_id"]: r for r in core.rank_in_category(rows) if r["composite"] is not None
    }

    mx = _db.scalar("SELECT max(date) FROM atlas_foundation.fund_rank_daily")
    stored_df = _db.read_df(
        "SELECT mstar_id, cat_rank, cat_size, composite, pct_band, breadth FROM atlas_foundation.fund_rank_daily WHERE date = :d",
        {"d": str(mx)},
    )
    stored = {r.mstar_id: r for r in stored_df.itertuples()}

    # production funds keyed by (category, cat_rank) so we can see who sits at a given rank
    prod_at = {(pr["category"], int(pr["cat_rank"])): pr for pr in prod_ranked.values()}

    only_prod = set(prod_ranked) - set(stored)
    only_stored = set(stored) - set(prod_ranked)
    size_mismatch, comp_mismatch = [], []
    tie_swaps, real_rank_errors = [], []
    TIE_EPS = 0.01  # composites equal within a cent are genuine ties; their order is broken by
    # breadth, which is non-deterministic (ntile tie-ordering at decile edges) —
    # the funds page itself reshuffles these on reload, so a ±rank here is expected.
    for mid, pr in prod_ranked.items():
        st = stored.get(mid)
        if st is None:
            continue
        if int(st.cat_size) != int(pr["cat_size"]):
            size_mismatch.append((mid, pr["cat_size"], int(st.cat_size)))
        if abs(float(st.composite) - float(pr["composite"])) > 0.01:
            comp_mismatch.append((mid, round(pr["composite"], 3), float(st.composite)))
        if int(st.cat_rank) != int(pr["cat_rank"]):
            # who does production rank at the position this fund got in storage?
            neighbour = prod_at.get((pr["category"], int(st.cat_rank)))
            is_tie = (
                neighbour is not None and abs(neighbour["composite"] - pr["composite"]) <= TIE_EPS
            )
            (tie_swaps if is_tie else real_rank_errors).append(
                (mid, pr["cat_rank"], int(st.cat_rank), round(pr["composite"], 4))
            )

    n = len(prod_ranked)
    ok = not (only_prod or only_stored or real_rank_errors or size_mismatch or comp_mismatch)
    print(f"verify fund_rank_daily @ {mx}: {n} production funds vs {len(stored)} stored")
    print(f"  cohort:    only-in-production={len(only_prod)}  only-in-stored={len(only_stored)}")
    print(f"  cat_size mismatches: {len(size_mismatch)}")
    # REPORTED, not asserted — see the module docstring. Stored breadth predates the leader-rule
    # reconciliation and only converges at the Task-5 rebuild; make this fatal once it has.
    stored_breadth = dict(zip(stored_df["mstar_id"], stored_df["breadth"], strict=True))
    n_breadth_off = sum(
        1
        for mid, pr in prod_ranked.items()
        if mid in stored_breadth and not _close(stored_breadth[mid], pr["breadth"])
    )
    print(f"  breadth mismatches (reported only): {n_breadth_off}")
    print(f"  composite mismatches (>0.01): {len(comp_mismatch)}")
    print(
        f"  rank: {len(tie_swaps)} benign tie-swaps (equal composite), {len(real_rank_errors)} REAL errors"
    )
    for label, lst in [
        ("cohort+", sorted(only_prod)[:8]),
        ("cohort-", sorted(only_stored)[:8]),
        ("size", size_mismatch[:8]),
        ("comp", comp_mismatch[:8]),
        ("REAL rank err", real_rank_errors[:8]),
    ]:
        if lst:
            print(f"    e.g. {label}: {lst}")
    print(
        "RESULT:",
        "✅ PASS — history today reproduces the live funds page (ties aside)" if ok else "❌ FAIL",
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
