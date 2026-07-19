#!/usr/bin/env python3
"""Desk outcome stamping + credibility layer (Desk v2 wave 2).

stamp_outcomes (moved from desk_run, extended): every past desk decision gets
T+5/20/60 marks as raw % AND alpha vs NIFTY 500 — reflection and credibility
learn from benchmark-relative results, so a broad rally is never miscredited
as skill. build_credibility distils the stamps into rolling per-desk /
per-charter / per-sector / per-decision-kind track records that are injected
into the PM's payload every cycle (TrustTrade-style measured credibility).
build_calibration compares stated conviction tiers to realized T+20 alpha.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db

M = "atlas_foundation"

_PX_SQL = f"""select o.close_adj from {M}.ohlcv_stock o
    join {M}.instrument_master i using (instrument_id)
    where i.symbol = :s and o.date <= :d order by o.date desc limit 1"""

_IDX_SQL = f"""select close from {M}.index_prices
    where index_code = 'NIFTY 500' and date <= :d order by date desc limit 1"""


def stamp_outcomes() -> None:
    """Nightly: mark every past desk decision with what ACTUALLY happened —
    raw % move and alpha vs NIFTY 500 since decision date. Booked orders and
    rejected/deferred proposals both get stamped (the road not taken too)."""
    sessions = _db.read_df(
        f"select date from {M}.index_prices where index_code='NIFTY 50' "
        "and date >= current_date - interval '8 months' order by date"
    )["date"].tolist()
    if len(sessions) < 6:
        return

    decisions = _db.read_df(
        f"""select dj.portfolio_id::text pid, dj.cycle_date,
                   a->>'symbol' symbol, a->>'side' side, 'order' as kind
            from {M}.desk_journal dj, jsonb_array_elements(dj.applied) a
            union
            select dj.portfolio_id::text, dj.cycle_date,
                   pr->>'symbol', pr->>'action', 'rejected'
            from {M}.desk_journal dj, jsonb_array_elements(dj.scout->'proposals') pr
            where pr->>'action' in ('add','exit')
              and not exists (select 1 from jsonb_array_elements(dj.applied) a2
                              where a2->>'symbol' = pr->>'symbol')
              and not exists (select 1 from jsonb_array_elements(coalesce(dj.queued, '[]'::jsonb)) q2
                              where q2->>'symbol' = pr->>'symbol')
            union
            select portfolio_id::text, cycle_date, symbol, side, 'order'
            from {M}.desk_pending_orders where status = 'booked'
            union
            select portfolio_id::text, cycle_date, symbol, side, 'rejected'
            from {M}.desk_pending_orders where status in ('rejected', 'expired')"""
    )
    n = 0
    for r in decisions.to_dict("records"):
        if r["cycle_date"] < sessions[0]:
            # older than the session window: stamps matured long ago — recomputing
            # with a truncated calendar would silently overwrite them with garbage
            continue
        base = _db.scalar(_PX_SQL, {"s": r["symbol"], "d": r["cycle_date"]})
        idx_base = _db.scalar(_IDX_SQL, {"d": r["cycle_date"]})
        if not base:
            continue
        stamps: dict[str, float] = {}
        later = [d for d in sessions if d > r["cycle_date"]]
        for col, horizon in (("t5", 5), ("t20", 20), ("t60", 60)):
            if len(later) < horizon:
                continue
            px = _db.scalar(_PX_SQL, {"s": r["symbol"], "d": later[horizon - 1]})
            if not px:
                continue
            pct = round((float(px) / float(base) - 1) * 100, 2)
            stamps[f"{col}_pct"] = pct
            idx_px = _db.scalar(_IDX_SQL, {"d": later[horizon - 1]})
            if idx_base and idx_px:
                idx_pct = (float(idx_px) / float(idx_base) - 1) * 100
                stamps[f"{col}_alpha"] = round(pct - idx_pct, 2)
        if not stamps:
            continue
        sets = ", ".join(f"{c} = :{c}" for c in stamps)
        _db.exec_sql(
            f"""insert into {M}.desk_outcomes (portfolio_id, kind, symbol, side, decision_date,
                    {", ".join(stamps)})
                values (:p, :k, :s, :sd, :d, {", ".join(":" + c for c in stamps)})
                on conflict (portfolio_id, kind, symbol, decision_date)
                do update set {sets}, stamped_at = now()""",
            {
                "p": r["pid"],
                "k": r["kind"],
                "s": r["symbol"],
                "sd": r["side"],
                "d": r["cycle_date"],
                **stamps,
            },
        )
        n += 1
    print(f"[desk] outcomes stamped: {n}", flush=True)


# a "hit" is positive alpha for buys/adds and NEGATIVE alpha avoided for
# exits/rejected sells — direction-aware so both sides of the book count.
# Scored on the longest MATURED horizon per decision (t20 once 20 sessions
# have elapsed, else t5) so track records exist from the desk's first week.
_CRED_SQL = f"""
with base as (
    select o.portfolio_id, o.kind, o.side, o.symbol,
           coalesce(o.t20_alpha, o.t5_alpha) alpha,
           m.params->>'charter' charter, i.sector
    from {M}.desk_outcomes o
    join {M}.portfolio_master m using (portfolio_id)
    left join {M}.instrument_master i
      on i.symbol = o.symbol and i.asset_class = 'stock'
    where coalesce(o.t20_alpha, o.t5_alpha) is not null
),
scored as (
    select *, case when side in ('buy', 'add') then alpha > 0
                   else alpha < 0 end as hit
    from base
)
select dim, dim_value, count(*) n,
       round(avg(case when hit then 1.0 else 0.0 end), 3) hit_rate,
       round(avg(alpha)::numeric, 2) avg_alpha
from (
    select 'desk' dim, portfolio_id::text dim_value, hit, alpha from scored
    union all select 'charter', charter, hit, alpha from scored where charter is not null
    union all select 'sector', sector, hit, alpha from scored where sector is not null
    union all select 'kind', kind || ':' || side, hit, alpha from scored
) d
group by 1, 2
"""


def _atomic_rebuild(table: str, cols: list[str], rows: list[dict], keymap: list[str]) -> None:
    """ONE delete+insert statement (CTE) so the rebuild commits atomically —
    a crash or concurrent reader never observes an empty/partial table."""
    if not rows:
        _db.exec_sql(f"delete from {M}.{table}")
        return
    values, params = [], {}
    for i, r in enumerate(rows):
        values.append("(" + ", ".join(f":p{i}_{j}" for j in range(len(cols))) + ")")
        for j, k in enumerate(keymap):
            params[f"p{i}_{j}"] = r[k]
    _db.exec_sql(
        f"""with del as (delete from {M}.{table})
            insert into {M}.{table} ({", ".join(cols)}) values {", ".join(values)}""",
        params,
    )


def build_credibility() -> int:
    rows = _db.read_df(_CRED_SQL).to_dict("records")
    _atomic_rebuild(
        "desk_credibility",
        ["dim", "dim_value", "n", "hit_rate", "avg_alpha"],
        rows,
        ["dim", "dim_value", "n", "hit_rate", "avg_alpha"],
    )
    print(f"[desk] credibility rows: {len(rows)}", flush=True)
    return len(rows)


def fetch_track_record(pid: str, charter: str) -> list[dict]:
    """The PM's measured-credibility payload: this desk, its charter, and every
    sector/kind track record with a real sample behind it."""
    df = _db.read_df(
        f"""select dim, dim_value, n, hit_rate, avg_alpha from {M}.desk_credibility
            where (dim = 'desk' and dim_value = :p) or (dim = 'charter' and dim_value = :c)
               or (dim in ('sector', 'kind') and n >= 5)
            order by dim, n desc""",
        {"p": pid, "c": charter},
    )
    return df.to_dict("records")


def compute_cvar(pid: str, tail_pct: float, floor_pct: float, min_sessions: int) -> dict:
    """FinCon-style within-episode tripwire: average of the worst tail_pct of
    daily NAV returns over the trailing ~6 months. Breaching floor_pct forces
    de-risk mode (no new entries) — enforced in hard_filter code, not prompt."""
    df = _db.read_df(
        f"""select nav from (
                select date, nav from {M}.portfolio_nav_daily
                where portfolio_id = :p and run_type = 'live'
                order by date desc limit 121) w
            order by date""",
        {"p": pid},
    )
    navs = [float(x) for x in df["nav"]]
    rets = [(b / a - 1) * 100 for a, b in itertools.pairwise(navs) if a > 0]
    if len(rets) < min_sessions:
        return {"state": "unarmed", "n": len(rets)}
    k = max(1, int(len(rets) * tail_pct))
    tail_avg = sum(sorted(rets)[:k]) / k
    state = "derisk" if tail_avg <= floor_pct else "normal"
    return {"state": state, "n": len(rets), "tail_avg": round(tail_avg, 2), "k": k}


def build_calibration() -> int:
    """Weekly: stated conviction tier vs realized T+20 alpha, per tier."""
    rows = _db.read_df(
        f"""with convs as (
                select dj.portfolio_id, dj.cycle_date, a->>'symbol' symbol,
                       (a->>'conviction')::int tier
                from {M}.desk_journal dj, jsonb_array_elements(dj.applied) a
                where a->>'conviction' ~ '^[1-5]$'
            )
            select c.tier, count(*) n,
                   round(avg(o.t20_alpha)::numeric, 2) avg_alpha,
                   round(avg(case when o.t20_alpha > 0 then 1.0 else 0.0 end), 3) hit_rate
            from convs c
            join {M}.desk_outcomes o
              on o.portfolio_id = c.portfolio_id and o.symbol = c.symbol
             and o.decision_date = c.cycle_date and o.kind = 'order'
            where o.t20_alpha is not null
            group by 1"""
    ).to_dict("records")
    _atomic_rebuild(
        "desk_calibration",
        ["tier", "n", "avg_alpha", "hit_rate"],
        rows,
        ["tier", "n", "avg_alpha", "hit_rate"],
    )
    print(f"[desk] calibration tiers: {len(rows)}", flush=True)
    return len(rows)


if __name__ == "__main__":
    stamp_outcomes()
    build_credibility()
