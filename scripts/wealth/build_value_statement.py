"""Per-client value statement: what the relationship has actually delivered,
plus what coaching could still recover.

Six components, all defaulting to 0 (never NULL) when a client has no rows in
a source, so every client in wealth.clients gets exactly one output row:

  sip_discipline_rs    realized. Value today of SIP units bought inside a
                        bench drawdown window, minus the cash paid for them —
                        the reward for not stopping the SIP through a crash.
  staying_power_rs     realized, non-panic clients only (panic_share < 0.10).
                        Units held at a drawdown-window start that were still
                        held at the window end (i.e. not sold into it) ×
                        NAV growth from window-end to today.
  advice_outcome_rs    realized. Sum of alpha_1y_rs across the client's
                        scored switches (wealth.advice_ledger).
  fee_save_yr_rs       realized/certain annual figure. Sum of est_value for
                        closet-index-style flags in wealth.client_flags.
  tax_headroom_rs       this-FY harvestable saving (wealth.tax_harvest).
  coaching_opportunity_rs  LABELLED UPPER BOUND, not realized: panic-loss
                        sells + dividend leakage + the stopped-SIP
                        counterfactual, each clamped >= 0 before summing.

Every component is floored at 0 in the stored row (a handful of clients have
net-negative advice alpha or a net-negative stopped-SIP counterfactual; the
value statement reports value delivered/recoverable, not a debit column —
the pre-floor number is not discarded, it just isn't a fit for this table).

Usage: .venv/bin/python scripts/wealth/build_value_statement.py
"""
from __future__ import annotations

import bisect
import sys
from collections import defaultdict

import pandas as pd
from behaviour_fingerprints import drawdown_windows
from engine_common import BENCH_ID, connect, nav_series
from psycopg2.extras import Json, execute_values


def load_navs(conn) -> dict[str, pd.Series]:
    navs = pd.read_sql(
        """select mstar_id, nav_date, nav::float nav from atlas_foundation.de_mf_nav_daily
           where mstar_id in (select distinct mstar_id from wealth.schemes where mstar_id is not null)
             and nav > 0""",
        conn,
    )
    navs["nav_date"] = pd.to_datetime(navs.nav_date)
    return {
        mid: g.sort_values("nav_date").drop_duplicates("nav_date", keep="last").set_index("nav_date").nav
        for mid, g in navs.groupby("mstar_id")
    }


def compute_all(conn) -> list[dict]:
    cur = conn.cursor()
    client_ids = pd.read_sql("select client_id from wealth.clients", conn).client_id.tolist()

    txns = pd.read_sql(
        """select t.client_id, t.scheme_id, t.folio, t.txn_date, t.txn_type,
                  t.units::float units, t.amount::float amount,
                  t.balance_units::float balance_units, s.mstar_id
           from wealth.transactions t
           left join wealth.schemes s using (scheme_id)
           where t.txn_date is not null
           order by t.client_id, t.scheme_id, t.folio, t.txn_date, t.txn_id""",
        conn,
    )
    txns["txn_date"] = pd.to_datetime(txns.txn_date)
    nav_by = load_navs(conn)

    bench = nav_series(conn, BENCH_ID)
    windows = drawdown_windows(bench)
    win_ts = [(pd.Timestamp(a), pd.Timestamp(b)) for a, b in windows]
    starts = [a for a, _ in win_ts]

    # ---- 1. sip_discipline_rs: SIP buys dated inside a drawdown window ----
    sip_disc: dict[int, float] = defaultdict(float)
    sip = txns[
        (txns.txn_type == "sip") & txns.mstar_id.notna()
        & txns.amount.notna() & (txns.amount > 0)
        & txns.units.notna() & (txns.units > 0)
    ]
    for r in sip.itertuples():
        i = bisect.bisect_right(starts, r.txn_date) - 1
        if i < 0 or r.txn_date > win_ts[i][1]:
            continue
        s = nav_by.get(r.mstar_id)
        if s is None or not len(s):
            continue
        nav_now = float(s.iloc[-1])
        sip_disc[r.client_id] += r.units * nav_now - r.amount

    # ---- 2. staying_power_rs: non-panic clients, held start->end of a window ----
    behaviour = pd.read_sql("select client_id, panic_share from wealth.client_behaviour", conn)
    non_panic = set(behaviour.loc[behaviour.panic_share.fillna(0) < 0.10, "client_id"])

    stay: dict[int, float] = defaultdict(float)
    mapped = txns[txns.mstar_id.notna()]
    for (cid, _sid, _folio), g in mapped.groupby(["client_id", "scheme_id", "folio"], sort=False):
        if cid not in non_panic:
            continue
        s_nav = nav_by.get(g.mstar_id.iloc[0])
        if s_nav is None or not len(s_nav):
            continue
        g = g.sort_values("txn_date")
        dates = g.txn_date.to_numpy()
        bals = g.balance_units.fillna(0.0).to_numpy()
        nav_today = float(s_nav.iloc[-1])
        for a, b in win_ts:
            ia = dates.searchsorted(a.to_datetime64(), side="right") - 1
            ib = dates.searchsorted(b.to_datetime64(), side="right") - 1
            if ia < 0 or ib < 0:
                continue
            held = min(bals[ia], bals[ib])
            if held <= 0:
                continue
            j = s_nav.index.searchsorted(b, side="right") - 1
            if j < 0:
                continue
            stay[cid] += held * (nav_today - float(s_nav.iloc[j]))

    # ---- 3. advice_outcome_rs ----
    adv = pd.read_sql(
        "select client_id, coalesce(sum(alpha_1y_rs),0)::float s from wealth.advice_ledger group by 1",
        conn,
    )
    advice = dict(zip(adv.client_id, adv.s))

    # ---- 4. fee_save_yr_rs: closet-index-style flags (verify rule text first) ----
    cur.execute("select distinct rule from wealth.client_flags order by 1")
    all_rules = [r[0] for r in cur.fetchall()]
    closet_rules = [r for r in all_rules if "closet" in r.lower()]
    if closet_rules:
        fee = pd.read_sql(
            "select client_id, sum(est_value)::float s from wealth.client_flags "
            "where rule like %s group by 1",
            conn, params=("%closet%",),
        )
        fee_save = dict(zip(fee.client_id, fee.s))
    else:
        fee_save = {}
        print(f"NOTE: no closet-index-style rule in wealth.client_flags; rules present: {all_rules}; "
              f"fee_save_yr_rs=0 for all clients")

    # ---- 5. tax_headroom_rs ----
    tax = pd.read_sql("select client_id, tax_saved_if_harvested::float s from wealth.tax_harvest", conn)
    tax_headroom = dict(zip(tax.client_id, tax.s))

    # ---- 6. coaching_opportunity_rs: panic loss + div leak + dead-SIP cf, each >= 0 ----
    beh = pd.read_sql(
        "select client_id, coalesce(panic_loss_out_rs,0)::float p, coalesce(div_leak_rs,0)::float d "
        "from wealth.client_behaviour",
        conn,
    )
    panic_map = dict(zip(beh.client_id, beh.p))
    leak_map = dict(zip(beh.client_id, beh.d))
    cfd = pd.read_sql("select client_id, coalesce(cf_sip_alive_rs,0)::float c from wealth.counterfactuals", conn)
    cf_map = dict(zip(cfd.client_id, cfd.c))

    rows = []
    for cid in client_ids:
        sip_v = max(0.0, sip_disc.get(cid, 0.0))
        stay_v = max(0.0, stay.get(cid, 0.0))
        adv_raw = advice.get(cid, 0.0)
        adv_v = max(0.0, adv_raw)
        fee_v = max(0.0, fee_save.get(cid, 0.0))
        tax_v = max(0.0, tax_headroom.get(cid, 0.0))
        panic_c = max(0.0, panic_map.get(cid, 0.0))
        leak_c = max(0.0, leak_map.get(cid, 0.0))
        sipcf_raw = cf_map.get(cid, 0.0)
        sipcf_c = max(0.0, sipcf_raw)
        coach_v = panic_c + leak_c + sipcf_c

        notes = []
        if cid not in non_panic:
            notes.append("staying_power_rs=0: client is in the drawdown-seller cohort (panic_share >= 0.10)")
        if not closet_rules:
            notes.append("no closet-index-style fee flag in wealth.client_flags; fee_save_yr_rs=0")
        if adv_raw < 0:
            notes.append(f"advice_outcome_rs floored at 0 (raw alpha sum ₹{round(adv_raw):,})")
        if sipcf_raw < 0:
            notes.append(f"dead-SIP counterfactual floored at 0 in coaching_opportunity (raw ₹{round(sipcf_raw):,})")

        summary = {
            "realized": {
                "sip_discipline_rs": round(sip_v),
                "staying_power_rs": round(stay_v),
                "advice_outcome_rs": round(adv_v),
                "fee_save_yr_rs": round(fee_v),
                "tax_headroom_rs": round(tax_v),
            },
            "opportunity": {
                "coaching_opportunity_rs": round(coach_v),
                "breakdown": {
                    "panic_loss_rs": round(panic_c),
                    "div_leak_rs": round(leak_c),
                    "dead_sip_cf_rs": round(sipcf_c),
                },
                "note": "upper bound: what coaching could have saved/recover, not money already banked",
            },
            "notes": notes,
        }
        rows.append(dict(
            client_id=int(cid),
            sip_discipline_rs=round(sip_v),
            staying_power_rs=round(stay_v),
            advice_outcome_rs=round(adv_v),
            fee_save_yr_rs=round(fee_v),
            tax_headroom_rs=round(tax_v),
            coaching_opportunity_rs=round(coach_v),
            summary=summary,
        ))
    return rows


def main() -> int:
    conn = connect()
    rows = compute_all(conn)

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.value_statements")
    cur.execute(
        """create table wealth.value_statements (
             client_id bigint primary key,
             sip_discipline_rs numeric(18,0), staying_power_rs numeric(18,0),
             advice_outcome_rs numeric(18,0), fee_save_yr_rs numeric(18,0),
             tax_headroom_rs numeric(18,0), coaching_opportunity_rs numeric(18,0),
             summary jsonb)"""
    )
    execute_values(
        cur,
        "insert into wealth.value_statements values %s",
        [(r["client_id"], r["sip_discipline_rs"], r["staying_power_rs"], r["advice_outcome_rs"],
          r["fee_save_yr_rs"], r["tax_headroom_rs"], r["coaching_opportunity_rs"], Json(r["summary"]))
         for r in rows],
        page_size=500,
    )
    cur.execute("revoke all on wealth.value_statements from anon, authenticated")
    conn.commit()

    n = len(rows)
    tot = {k: sum(r[k] for r in rows) for k in
           ("sip_discipline_rs", "staying_power_rs", "advice_outcome_rs",
            "fee_save_yr_rs", "tax_headroom_rs", "coaching_opportunity_rs")}
    print(f"value statements: {n} clients")
    print(f"  sip_discipline_rs       ₹{tot['sip_discipline_rs'] / 1e7:.2f} cr")
    print(f"  staying_power_rs        ₹{tot['staying_power_rs'] / 1e7:.2f} cr")
    print(f"  advice_outcome_rs       ₹{tot['advice_outcome_rs'] / 1e7:.2f} cr")
    print(f"  fee_save_yr_rs          ₹{tot['fee_save_yr_rs'] / 1e5:.1f} L/yr")
    print(f"  tax_headroom_rs         ₹{tot['tax_headroom_rs'] / 1e5:.1f} L")
    print(f"  coaching_opportunity_rs ₹{tot['coaching_opportunity_rs'] / 1e7:.2f} cr (upper bound, not realized)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
