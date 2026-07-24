"""Behaviour segmentation: one PRIMARY segment per client + independent
trait chips + a ₹ what-if — the cohort-dashboard/client-360 identity band.

Precedence (first match wins — every client in wealth.clients gets exactly
one segment, counts sum to the full client count):

  1. Too New to Tell   no wealth.client_behaviour row AND no
                       wealth.client_benchmark row — not enough history to
                       fingerprint or benchmark yet.
  2. Crash Sellers / Dividend Spenders / SIP Quitters
                       whichever of {panic_loss_out_rs, div_leak_rs,
                       cf_sip_alive_rs} is the client's largest ₹ cost, when
                       that max clears the materiality floor
                       (atlas_thresholds.wealth_segment_material_cost_rs,
                       seeded ₹50,000 idempotently — mirrors
                       build_call_lists.load_armed_floor()).
  3. Drifted Away      disengaged per build_call_lists.py's own disengaged
                       basis (wealth.client_churn_risk: no fresh money in
                       DISENGAGED_QUIET_MONTHS+ and SIPs stopped), no
                       dominant cost above the floor.
  4. Steady Compounders  everyone else.

`traits` (jsonb) are INDEPENDENT chips, not the primary segment restated —
a client can carry several regardless of which one won precedence (e.g. a
Crash Seller whose div_leak_rs also clears the floor still gets the
div_spender chip). chaser/high_churn_risk have no primary segment of their
own; chasers stay a trait only (no ₹ cost column exists for chasing).

`whatif_rs` = sum of the client's >=0 cost components among
{panic_loss_out_rs, div_leak_rs, cf_sip_alive_rs} — a labelled upper bound,
same semantics as value_statements.coaching_opportunity_rs (but computed
independently here, not copied).

Usage: .venv/bin/python scripts/wealth/build_segments.py
"""

from __future__ import annotations

import sys
from decimal import Decimal

import pandas as pd
from engine_common import connect
from psycopg2.extras import Json, execute_values

MATERIAL_COST_FLOOR_KEY = "wealth_segment_material_cost_rs"
MATERIAL_COST_FLOOR_DEFAULT = 50_000  # fallback only if the seed insert below can't run

# Documented demo heuristics (not DB-driven — v1 precedent, see build_call_lists.py):
CHASER_MIN_SHARE = 0.25  # chase_hot_share >= this -> chaser trait
DISENGAGED_QUIET_MONTHS = 12  # no fresh money in this many months...
DISENGAGED_SIP_STOP_MIN_SHARE = (
    1.0  # ...and SIPs stopped (fully; no SIP history counts as "stopped" too)
)
CHURN_TOP_QUARTILE = 0.75  # high_churn_risk = top quartile of disengagement_score

SEGMENTS = (
    "Too New to Tell",
    "Crash Sellers",
    "Dividend Spenders",
    "SIP Quitters",
    "Drifted Away",
    "Steady Compounders",
)


def load_material_cost_floor(cur) -> float:
    """Idempotent bootstrap: seed wealth_segment_material_cost_rs into
    atlas_foundation.atlas_thresholds if absent (no unique constraint on
    threshold_key there, so "insert ... where not exists" stands in for ON
    CONFLICT — exact mirror of build_call_lists.load_armed_floor())."""
    cur.execute(
        """insert into atlas_foundation.atlas_thresholds
             (threshold_key, threshold_value, category, description, units,
              default_value, is_active, created_at, last_modified_by, last_modified_at)
           select %(k)s, %(v)s, 'wealth',
                  'Minimum rupee cost (panic loss / dividend leak / dead-SIP what-if) for it to '
                  'name a client''s dominant-cost segment in wealth.client_segments', 'rupees', %(v)s,
                  true, now(), 'system', now()
           where not exists (
             select 1 from atlas_foundation.atlas_thresholds where threshold_key = %(k)s)""",
        {"k": MATERIAL_COST_FLOOR_KEY, "v": MATERIAL_COST_FLOOR_DEFAULT},
    )
    cur.execute(
        "select threshold_value from atlas_foundation.atlas_thresholds where threshold_key = %s",
        (MATERIAL_COST_FLOOR_KEY,),
    )
    row = cur.fetchone()
    return float(row[0]) if row else MATERIAL_COST_FLOOR_DEFAULT


def compute_all(conn) -> list[dict]:
    cur = conn.cursor()
    floor = load_material_cost_floor(cur)
    conn.commit()

    client_ids = pd.read_sql("select client_id from wealth.clients", conn).client_id.tolist()

    beh = pd.read_sql(
        "select client_id, panic_loss_out_rs::float p, div_leak_rs::float d, "
        "chase_hot_share::float chase from wealth.client_behaviour",
        conn,
    ).set_index("client_id")
    has_beh = set(beh.index)
    # NULL -> 0 for all three: no evidence of the cost/behaviour is not evidence
    # of it being nonzero (same convention build_call_lists.py documents for
    # chase_hot_share; panic_loss_out_rs/div_leak_rs have no NULLs in practice).
    beh[["p", "d", "chase"]] = beh[["p", "d", "chase"]].fillna(0.0)

    bench_ids = set(pd.read_sql("select client_id from wealth.client_benchmark", conn).client_id)

    cf = (
        pd.read_sql("select client_id, cf_sip_alive_rs::float c from wealth.counterfactuals", conn)
        .set_index("client_id")
        .c.fillna(0.0)
    )

    churn = pd.read_sql(
        "select client_id, months_since_inflow::float months, sip_stop_share::float sip_stop, "
        "disengagement_score::float score from wealth.client_churn_risk",
        conn,
    ).set_index("client_id")
    churn_quartile = churn.score.quantile(CHURN_TOP_QUARTILE) if len(churn) else None

    rows = []
    for cid in client_ids:
        p = float(beh.p.get(cid, 0.0))
        d = float(beh.d.get(cid, 0.0))
        c = float(cf.get(cid, 0.0))
        chase = float(beh.chase.get(cid, 0.0))

        # traits: independent chips, computed regardless of primary segment
        traits = {
            "crash_seller": p >= floor,
            "chaser": chase >= CHASER_MIN_SHARE,
            "div_spender": d >= floor,
            "sip_quitter": c >= floor,
            "disengaged": False,
            "high_churn_risk": False,
        }
        if cid in churn.index:
            row = churn.loc[cid]
            traits["disengaged"] = bool(
                row.months >= DISENGAGED_QUIET_MONTHS
                and (pd.isna(row.sip_stop) or row.sip_stop >= DISENGAGED_SIP_STOP_MIN_SHARE)
            )
            if churn_quartile is not None:
                traits["high_churn_risk"] = bool(row.score >= churn_quartile)

        # primary segment: precedence, first match wins
        if cid not in has_beh and cid not in bench_ids:
            segment = "Too New to Tell"
            reason = "No behaviour fingerprint or benchmark yet — too new to assess."
        elif max(p, d, c) >= floor:
            # tie-break (no ties observed in real data): panic > div leak > dead-SIP
            if p >= d and p >= c:
                segment = "Crash Sellers"
                reason = f"Sold ₹{p / 1e5:.1f}L at a loss during market falls — their largest controllable cost."
            elif d >= c:
                segment = "Dividend Spenders"
                reason = (
                    f"₹{d / 1e5:.1f}L leaked out via dividend payouts instead of staying invested."
                )
            else:
                segment = "SIP Quitters"
                reason = f"Stopping their SIP cost an estimated ₹{c / 1e5:.1f}L versus staying the course."
        elif traits["disengaged"]:
            segment = "Drifted Away"
            months = churn.loc[cid].months
            reason = f"No fresh money in {months:.0f} months and SIPs stopped — drifting from the relationship."
        else:
            segment = "Steady Compounders"
            reason = "No dominant cost above the materiality floor, actively engaged — compounding steadily."

        whatif = sum(Decimal(str(x)) for x in (p, d, c) if x >= 0)

        rows.append(
            dict(
                client_id=int(cid),
                segment=segment,
                reason=reason,
                whatif_rs=int(whatif.to_integral_value()),
                traits=traits,
            )
        )
    return rows


def main() -> int:
    conn = connect()
    rows = compute_all(conn)

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.client_segments")
    cur.execute(
        """create table wealth.client_segments (
             client_id bigint primary key,
             segment text, reason text,
             whatif_rs numeric(18,0), traits jsonb)"""
    )
    execute_values(
        cur,
        "insert into wealth.client_segments values %s",
        [
            (r["client_id"], r["segment"], r["reason"], r["whatif_rs"], Json(r["traits"]))
            for r in rows
        ],
        page_size=500,
    )
    cur.execute("revoke all on wealth.client_segments from anon, authenticated")
    conn.commit()

    n = len(rows)
    counts = pd.Series([r["segment"] for r in rows]).value_counts()
    cur.execute(
        "select threshold_value from atlas_foundation.atlas_thresholds where threshold_key = %s",
        (MATERIAL_COST_FLOOR_KEY,),
    )
    floor = float(cur.fetchone()[0])
    print(
        f"client_segments: {n} clients (material-cost floor ₹{floor:,.0f} "
        f"from atlas_thresholds.{MATERIAL_COST_FLOOR_KEY})"
    )
    for seg in SEGMENTS:
        print(f"  {seg:20s} {counts.get(seg, 0)}")
    assert int(counts.sum()) == n, "segment counts must sum to client count"

    trait_counts = {
        k: sum(1 for r in rows if r["traits"][k])
        for k in (
            "crash_seller",
            "chaser",
            "div_spender",
            "sip_quitter",
            "disengaged",
            "high_churn_risk",
        )
    }
    print("traits (independent, can overlap):")
    for k, v in trait_counts.items():
        print(f"  {k:16s} {v}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
