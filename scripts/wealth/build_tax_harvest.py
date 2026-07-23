"""Per-client FY tax-harvest sheet: gain-harvest headroom in the Rs 1.25L LTCG
exemption (use-it-or-lose-it, resets 1 Apr; no wash-sale rule in India), loss
candidates gated by the exemption-before-set-off rule, carry-forward ledger.
Usage: .venv/bin/python scripts/wealth/build_tax_harvest.py
"""
from __future__ import annotations
import json, sys
from datetime import date
from decimal import Decimal
from engine_common import connect
from psycopg2.extras import execute_values, Json


def load_rates(cur):
    cur.execute("""select threshold_key, threshold_value from atlas_foundation.atlas_thresholds
                   where threshold_key in ('portfolio_tax_ltcg_exemption_inr','portfolio_tax_ltcg_pct')""")
    m = dict(cur.fetchall())
    return Decimal(str(m["portfolio_tax_ltcg_exemption_inr"])), Decimal(str(m["portfolio_tax_ltcg_pct"]))


EXEMPT = None  # set in main/compute via load_rates; tests import after first call


def current_fy_start(today=None) -> date:
    t = today or date.today()
    return date(t.year if t.month >= 4 else t.year - 1, 4, 1)


def indian_fy_label(d: date) -> str:
    s = d.year if d.month >= 4 else d.year - 1
    return f"FY{s % 100:02d}-{(s + 1) % 100:02d}"


def compute_client(conn, cid):
    global EXEMPT
    cur = conn.cursor()
    if EXEMPT is None:
        EXEMPT, _ = load_rates(cur)
    exempt, ltcg_rate = load_rates(cur)
    fy0 = current_fy_start()
    cur.execute("""select coalesce(sum(l.realized_gain),0) from wealth.lots l
                   join wealth.schemes s using (scheme_id)
                   where l.client_id=%s and l.status='closed' and s.asset_class='Equity'
                     and l.tax_bucket='ltcg' and l.sell_date >= %s and l.realized_gain > 0""",
                (cid, fy0))
    realized = Decimal(str(cur.fetchone()[0]))
    headroom = max(Decimal(0), exempt - realized)
    cur.execute("""select l.lot_id, l.fund_name, l.buy_date, l.units, l.unit_basis, l.nav_now,
                          l.unrealized_gain
                   from wealth.lots l join wealth.schemes s using (scheme_id)
                   where l.client_id=%s and l.status='open' and s.asset_class='Equity'
                     and l.tax_bucket='ltcg' and l.unrealized_gain > 0
                   order by l.buy_date nulls first""", (cid,))
    gains, used = [], Decimal(0)
    for lot_id, fn, bd, units, basis, nav, ug in cur.fetchall():
        if used >= headroom:
            break
        take_gain = min(Decimal(str(ug)), headroom - used)
        frac = take_gain / Decimal(str(ug))
        gains.append(dict(lot_id=lot_id, fund=fn[:60], buy_date=str(bd),
                          units=round(float(units) * float(frac), 3),
                          gain=round(float(take_gain)), bucket="ltcg"))
        used += take_gain
    # losses: only actionable when realized LTCG beyond exemption exists
    cur.execute("""select l.lot_id, l.fund_name, l.unrealized_gain from wealth.lots l
                   join wealth.schemes s using (scheme_id)
                   where l.client_id=%s and l.status='open' and s.asset_class='Equity'
                     and l.unrealized_gain < -5000 order by l.unrealized_gain limit 10""", (cid,))
    losses = [dict(lot_id=i, fund=f[:60], loss=round(float(g))) for i, f, g in cur.fetchall()]
    loss_note = ("actionable: realized gains exceed the exemption — set-off saves 12.5%"
                 if realized > exempt else
                 "hold: gains are within the tax-free band; harvesting losses now only "
                 "creates a carry-forward (8 years, needs on-time ITR)")
    # carry-forward: net realized losses by FY (informational)
    cur.execute("""select coalesce(sum(realized_gain),0) from wealth.lots
                   where client_id=%s and status='closed' and realized_gain < 0
                     and sell_date >= %s""", (cid, fy0))
    cf = Decimal(str(cur.fetchone()[0]))
    return dict(fy=indian_fy_label(fy0), realized_ltcg=round(float(realized)),
                headroom=round(float(headroom)), gain_candidates=gains,
                gain_value=round(float(used)),
                tax_saved_if_harvested=round(float(used * ltcg_rate)),
                loss_candidates=losses, loss_note=loss_note,
                carry_forward=round(float(-cf)))


def main() -> int:
    conn = connect()
    cur = conn.cursor()
    cur.execute("select distinct client_id from wealth.lots where status='open'")
    cids = [r[0] for r in cur.fetchall()]
    rows = []
    for cid in cids:
        r = compute_client(conn, cid)
        rows.append((cid, r["fy"], r["realized_ltcg"], r["headroom"], Json(r["gain_candidates"]),
                     r["gain_value"], r["tax_saved_if_harvested"], Json(r["loss_candidates"]),
                     r["loss_note"], r["carry_forward"]))
    cur.execute("drop table if exists wealth.tax_harvest")
    cur.execute("""create table wealth.tax_harvest (
        client_id bigint primary key, fy text, realized_ltcg numeric(18,0),
        headroom numeric(18,0), gain_candidates jsonb, gain_value numeric(18,0),
        tax_saved_if_harvested numeric(18,0), loss_candidates jsonb, loss_note text,
        carry_forward numeric(18,0))""")
    execute_values(cur, "insert into wealth.tax_harvest values %s", rows, page_size=500)
    cur.execute("revoke all on wealth.tax_harvest from anon, authenticated")
    conn.commit()
    tot = sum(r[6] for r in rows)
    print(f"tax harvest: {len(rows)} clients, cohort tax-saved-if-harvested ₹{tot/1e5:.1f}L this FY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
