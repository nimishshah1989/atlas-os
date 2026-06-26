#!/usr/bin/env python3
"""Create the ON-READ composite view — the permanent fix for editable weights.

`atlas.atlas_lens_scores_v` is a drop-in over `atlas_lens_scores_daily`: every
stored column passes through UNCHANGED, except composite / conviction_tier /
coverage_factor / lenses_active, which are computed ON READ from the (materialized,
immutable) lens sub-scores × the LIVE weights in atlas_thresholds. So editing a
weight is instant — zero rows rewritten, ever — and the value always reflects the
current DB weights. Verified identical to the canonical compute_composite (the same
rescale → coverage-weighted avg → convergence → valuation-multiplier logic);
policy excluded (FYI), valuation is the multiplier.

    python create_composite_view.py            # create/replace the view
    python create_composite_view.py --verify   # + reconcile the view to compute_composite
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import _db  # noqa: E402
from recompute_sql import CONV, _rescale_sql  # noqa: E402

# pass-through columns (everything except the four computed ones)
_PASSTHROUGH = [
    "instrument_id",
    "date",
    "asset_class",
    "technical",
    "fundamental",
    "valuation",
    "catalyst",
    "flow",
    "policy",
    "tech_trend",
    "tech_rs",
    "tech_vol_contraction",
    "tech_volume",
    "fund_profitability",
    "fund_margin",
    "fund_growth",
    "fund_balance_sheet",
    "fund_op_leverage",
    "val_pe_vs_sector",
    "val_absolute_pe",
    "val_pb",
    "val_ev_ebitda",
    "val_52w_position",
    "cat_earnings_strategy",
    "cat_capital_action",
    "cat_governance",
    "flow_promoter",
    "flow_institutional",
    "flow_smart_money",
    "policy_tailwind",
    "valuation_zone",
    "valuation_multiplier",
    "smart_money_score",
    "degradation_score",
    "risk_flags",
    "evidence",
    "compute_run_id",
    "computed_at",
]


def _cfg_cte() -> str:
    def g(key, default):
        return f"coalesce(max(threshold_value) FILTER (WHERE threshold_key='{key}'), {default})"

    return f"""cfg AS (SELECT
      {g("lens_weight_technical", 0)} wt, {g("lens_weight_fundamental", 0)} wf,
      {g("lens_weight_catalyst", 0)} wc, {g("lens_weight_flow", 0)} wfl,
      {g("lens_convergence_threshold", 40)} conv_thr, {g("lens_convergence_2", 1.06)} c2,
      {g("lens_convergence_3", 1.10)} c3, {g("lens_convergence_4plus", 1.15)} c4,
      {g("lens_conviction_highest_score", 70)} hi_s, {g("lens_conviction_highest_min_layers", 3)} hi_l,
      {g("lens_conviction_high_score", 58)} h_s, {g("lens_conviction_high_min_layers", 2)} h_l,
      {g("lens_conviction_medium_score", 45)} m_s, {g("lens_conviction_watch_score", 30)} wa_s
    FROM atlas.atlas_thresholds)"""


def build_view_sql() -> str:
    wmap = {"technical": "wt", "fundamental": "wf", "catalyst": "wc", "flow": "wfl"}
    resc = ",\n".join(f"      {_rescale_sql(l)} AS r_{l}" for l in CONV)
    tw = " + ".join(f"(CASE WHEN r_{l} IS NOT NULL THEN {wmap[l]} ELSE 0 END)" for l in CONV)
    wsum = " + ".join(
        f"(CASE WHEN r_{l} IS NOT NULL THEN r_{l}*{wmap[l]} ELSE 0 END)" for l in CONV
    )
    convn = " + ".join(f"(CASE WHEN r_{l} >= conv_thr THEN 1 ELSE 0 END)" for l in CONV)
    la = " + ".join(f"(CASE WHEN r_{l} IS NOT NULL THEN 1 ELSE 0 END)" for l in CONV)
    passthrough = ", ".join(_PASSTHROUGH)
    l_passthrough = ", ".join(f"l.{c}" for c in _PASSTHROUGH)
    comp_expr = (
        "round(LEAST(100, GREATEST(0, LEAST(100, GREATEST(0, wavg*cm))*vm "
        "+ COALESCE(smart_money_score,0) + COALESCE(degradation_score,0)))::numeric, 2)"
    )
    return f"""CREATE OR REPLACE VIEW atlas.atlas_lens_scores_v AS
WITH {_cfg_cte()},
r AS (
  SELECT {l_passthrough}, cfg.*,
{resc}
  FROM atlas.atlas_lens_scores_daily l CROSS JOIN cfg
),
a AS (
  SELECT *, ({tw})::numeric tw, ({wsum})::numeric wsum,
         ({convn})::int conv_n, ({la})::int la
  FROM r
),
c AS (
  SELECT *,
    CASE WHEN tw>0 THEN (wsum/tw)*sqrt(tw) ELSE 0 END wavg,
    sqrt(tw) cov,
    CASE WHEN conv_n>=4 THEN c4 WHEN conv_n>=3 THEN c3 WHEN conv_n>=2 THEN c2 ELSE 1.0 END cm,
    LEAST(1.15, GREATEST(0.75, COALESCE(valuation_multiplier,1.0))) vm
  FROM a
),
f AS (SELECT *, {comp_expr} AS composite, round(cov::numeric,2) AS coverage_factor, la AS lenses_active FROM c)
SELECT {passthrough}, composite, coverage_factor, lenses_active,
  CASE WHEN composite >= hi_s AND lenses_active >= hi_l THEN 'HIGHEST'
       WHEN composite >= h_s AND lenses_active >= h_l THEN 'HIGH'
       WHEN composite >= m_s THEN 'MEDIUM'
       WHEN composite >= wa_s THEN 'WATCH'
       ELSE 'BELOW_THRESHOLD' END AS conviction_tier
FROM f"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    sql = build_view_sql()
    _db.exec_sql(sql)
    print("✅ created view atlas.atlas_lens_scores_v")
    if args.verify:
        import pandas as pd

        from atlas.db import load_thresholds
        from atlas.lenses.compute.composite import compute_composite
        from atlas.lenses.compute.thresholds_view import nest_thresholds

        # max(date) from the BASE table (indexed, fast) — never aggregate over the view
        mx = _db.scalar(
            "SELECT max(date) FROM atlas.atlas_lens_scores_daily WHERE asset_class='stock'"
        )
        import time as _t

        _t0 = _t.time()
        v = _db.read_df(
            "SELECT * FROM atlas.atlas_lens_scores_v WHERE asset_class='stock' AND date=:d",
            {"d": mx},
        ).set_index("instrument_id")
        print(f"  per-date view query: {len(v)} rows in {_t.time() - _t0:.2f}s")
        raw = load_thresholds()
        thn = nest_thresholds(
            {k: (float(x) if isinstance(x, Decimal) else x) for k, x in raw.items()}
        )

        def f(x):
            return float(x) if x is not None and pd.notna(x) else None

        bad = 0
        for iid in v.index[:500]:
            r = v.loc[iid]
            c = compute_composite(
                technical=f(r.technical),
                fundamental=f(r.fundamental),
                valuation_score=f(r.valuation),
                catalyst=f(r.catalyst),
                flow=f(r.flow),
                policy=f(r.policy),
                valuation_multiplier=f(r.valuation_multiplier) or 1.0,
                smart_money_score=f(r.smart_money_score) or 0.0,
                degradation_score=f(r.degradation_score) or 0.0,
                thresholds=thn,
            )
            if (
                abs(float(r.composite) - float(c.final_score)) > 0.1
                or r.conviction_tier != c.conviction_tier
            ):
                bad += 1
                if bad <= 5:
                    print(
                        f"  mismatch {iid}: view {r.composite}/{r.conviction_tier} vs "
                        f"canonical {c.final_score}/{c.conviction_tier}"
                    )
        print(f"  verify: {500 - bad}/500 match compute_composite (composite+tier) on {mx}")
        sys.exit(0 if bad == 0 else 1)


if __name__ == "__main__":
    main()
