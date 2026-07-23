"""FIFO lot ledger: wealth.transactions → wealth.lots (exact CG basis per lot).

Same FIFO mechanics as atlas/portfolio/tax.py (deque per position, oldest first),
extended with what real MF ledgers need: 31-Jan-2018 equity grandfathering,
per-asset-class LTCG holding windows, dividend-reinvest cost = net reinvested
(units × NAV), bonus units at zero cost, approx opening-balance lots.

One row per FIFO slice:
  closed slices — buy leg matched to the sell leg that consumed it, with realized
  gain, holding days and st/lt bucket;
  open slices — remaining units with unrealized gain at the scheme's latest NAV
  and tax_if_sold_now under current rates (equity rates from atlas_thresholds
  'portfolio', non-equity from 'wealth' rows).

Grandfathering: equity lots bought < 31-Jan-2018 get basis/unit
max(cost, min(nav_31jan18, exit price)) — the CBDT formula — when the scheme has
NAV history; without NAV the raw cost stands (conservative, counted in report).
Opening-balance lots (approx=true): buy_date unknown → treated long-term; cost =
units × first dated NAV seen in the same fund-folio (approximation carried in
the approx flag; never silently).

Usage: .venv/bin/python scripts/wealth/build_lots.py
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict, deque
from datetime import date, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values

D = Decimal
BUY_TYPES = {"purchase", "sip", "switch_in", "div_reinvest", "bonus", "opening_balance",
             "dtp_in", "transfer_in", "merger_in", "transmission_in", "balance_adjust"}
SELL_TYPES = {"redemption", "switch_out", "swp", "transfer_out", "merger_out",
              "transmission_out", "balance_adjust"}
GF_DATE = date(2018, 1, 31)


def load_rates(cur) -> dict:
    cur.execute(
        """select threshold_key, threshold_value from atlas_foundation.atlas_thresholds
           where category in ('portfolio', 'wealth') and is_active"""
    )
    m = {k: D(str(v)) for k, v in cur.fetchall()}
    return {
        "eq_stcg": m["portfolio_tax_stcg_pct"],
        "eq_ltcg": m["portfolio_tax_ltcg_pct"],
        "eq_ltcg_days": int(m["portfolio_tax_ltcg_days"]),
        "ne_slab": m["wealth_tax_nonequity_slab_pct"],
        "ne_ltcg_days": int(m["wealth_tax_nonequity_ltcg_days"]),
    }


def main() -> int:
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    rates = load_rates(cur)

    cur.execute(
        """select s.scheme_id, s.asset_class, s.mstar_id from wealth.schemes s"""
    )
    scheme_class = {sid: (ac, mid) for sid, ac, mid in cur.fetchall()}

    # NAV lookups: 31-Jan-2018 FMV (nearest on/before) + latest NAV per mapped scheme
    cur.execute(
        """select distinct on (mstar_id) mstar_id, nav
           from atlas_foundation.de_mf_nav_daily
           where nav_date <= %s and nav_date >= %s
           order by mstar_id, nav_date desc""",
        (GF_DATE, GF_DATE - timedelta(days=14)),
    )
    gf_nav = {mid: D(str(v)) for mid, v in cur.fetchall()}
    cur.execute(
        """select distinct on (mstar_id) mstar_id, nav_date, nav
           from atlas_foundation.de_mf_nav_daily
           order by mstar_id, nav_date desc"""
    )
    last_nav = {mid: (d_, D(str(v))) for mid, d_, v in cur.fetchall()}

    cur.execute(
        """select txn_id, client_id, scheme_id, isin, fund_name, folio, txn_date, txn_type,
                  nav, units, amount, stamp_duty, is_debit, approx
           from wealth.transactions
           order by client_id, coalesce(scheme_id, 0), fund_name, folio,
                    txn_date nulls first, txn_id"""
    )
    txns = cur.fetchall()
    groups: dict[tuple, list] = defaultdict(list)
    for t in txns:
        groups[(t[1], t[2], t[4], t[5])].append(t)  # client, scheme, fund_name, folio

    out_rows = []
    n_gf_applied = n_gf_missing = n_oversell = 0
    for (client_id, scheme_id, fund_name, folio), rows in groups.items():
        ac, mid = scheme_class.get(scheme_id, (None, None))
        is_equity = ac == "Equity"
        ltcg_days = rates["eq_ltcg_days"] if is_equity else rates["ne_ltcg_days"]
        fmv = gf_nav.get(mid) if is_equity and mid else None
        lnav = last_nav.get(mid) if mid else None
        first_nav = next((D(str(r[8])) for r in rows if r[8] is not None and r[6] is not None), None)
        lots: deque = deque()  # (buy_date|None, units, unit_cost|None, buy_txn_id, buy_type, approx)
        for (
            txn_id, _cid, _sid, _isin, _fn, _fo, txn_date, txn_type,
            nav, units, amount, stamp_duty, is_debit, approx,
        ) in rows:
            nav = D(str(nav)) if nav is not None else None
            units = D(str(units)) if units is not None else None
            amount = D(str(amount)) if amount is not None else None
            if txn_type in BUY_TYPES and not is_debit:
                if not units or units == 0:
                    continue
                if txn_type == "opening_balance":
                    unit_cost = first_nav  # approx: first dated NAV in this fund-folio
                elif txn_type == "div_reinvest":
                    unit_cost = nav  # net reinvested = units × NAV (post TDS/DDT)
                elif txn_type == "bonus":
                    unit_cost = D("0")
                elif amount is not None:
                    unit_cost = amount / units  # incl. stamp duty = cost of acquisition
                else:
                    unit_cost = nav
                lots.append((txn_date, units, unit_cost, txn_id, txn_type, bool(approx)))
            elif txn_type in SELL_TYPES and is_debit:
                if not units or units == 0:
                    continue
                sell_pu = (amount / units) if amount else nav
                remaining = units
                while remaining > D("0.0005") and lots:
                    b_date, b_units, b_cost, b_txn, b_type, b_approx = lots[0]
                    take = min(remaining, b_units)
                    # grandfathered basis per CBDT: max(cost, min(FMV_31Jan18, sale price))
                    basis = b_cost
                    gf_applied = False
                    if fmv is not None and (b_date is None or b_date < GF_DATE) and b_cost is not None and sell_pu is not None:
                        basis = max(b_cost, min(fmv, sell_pu))
                        gf_applied = basis != b_cost
                        n_gf_applied += gf_applied
                    if is_equity and (b_date is None or b_date < GF_DATE) and fmv is None and mid:
                        n_gf_missing += 1
                    days = (txn_date - b_date).days if (txn_date and b_date) else None
                    long_term = days >= ltcg_days if days is not None else True  # openers = LT
                    gain = (
                        (sell_pu - basis) * take
                        if (sell_pu is not None and basis is not None)
                        else None
                    )
                    out_rows.append(
                        (
                            client_id, scheme_id, fund_name, folio, "closed",
                            b_date, b_type, b_txn,
                            float(take), float(b_cost) if b_cost is not None else None,
                            float(basis) if basis is not None else None, gf_applied,
                            txn_date, txn_type, txn_id,
                            float(sell_pu) if sell_pu is not None else None,
                            float(gain) if gain is not None else None,
                            days, "ltcg" if long_term else "stcg",
                            None, None, None, b_approx,
                        )
                    )
                    if take == b_units:
                        lots.popleft()
                    else:
                        lots[0] = (b_date, b_units - take, b_cost, b_txn, b_type, b_approx)
                    remaining -= take
                if remaining > D("0.0005"):
                    n_oversell += 1
            # dividends/segregation/other: no lot effect

        asof, cur_nav = (lnav if lnav else (None, None))
        for b_date, b_units, b_cost, b_txn, b_type, b_approx in lots:
            days = (asof - b_date).days if (asof and b_date) else None
            long_term = days >= ltcg_days if days is not None else True
            basis = b_cost
            gf_applied = False
            if fmv is not None and (b_date is None or b_date < GF_DATE) and b_cost is not None and cur_nav is not None:
                basis = max(b_cost, min(fmv, cur_nav))
                gf_applied = basis != b_cost
            unreal = (cur_nav - basis) * b_units if (cur_nav is not None and basis is not None) else None
            if unreal is not None and unreal > 0:
                rate = (
                    (rates["eq_ltcg"] if long_term else rates["eq_stcg"])
                    if is_equity
                    else (rates["ne_slab"])
                )
                tax_now = unreal * rate  # per-lot provisional (LTCG exemption is per taxpayer-FY)
            else:
                tax_now = D("0") if unreal is not None else None
            out_rows.append(
                (
                    client_id, scheme_id, fund_name, folio, "open",
                    b_date, b_type, b_txn,
                    float(b_units), float(b_cost) if b_cost is not None else None,
                    float(basis) if basis is not None else None, gf_applied,
                    None, None, None, None, None, days,
                    "ltcg" if long_term else "stcg",
                    float(cur_nav) if cur_nav is not None else None,
                    float(unreal) if unreal is not None else None,
                    float(tax_now) if tax_now is not None else None, b_approx,
                )
            )

    cur.execute("drop table if exists wealth.lots")
    cur.execute(
        """create table wealth.lots (
             lot_id bigint generated always as identity primary key,
             client_id bigint not null references wealth.clients(client_id),
             scheme_id bigint references wealth.schemes(scheme_id),
             fund_name text not null, folio text not null,
             status text not null,            -- open | closed
             buy_date date, buy_type text, buy_txn_id bigint,
             units numeric(20,3) not null,
             unit_cost numeric(16,4), unit_basis numeric(16,4), gf_applied boolean not null,
             sell_date date, sell_type text, sell_txn_id bigint,
             sell_price numeric(16,4),
             realized_gain numeric(18,2), holding_days int,
             tax_bucket text not null,        -- ltcg | stcg
             nav_now numeric(16,4), unrealized_gain numeric(18,2),
             tax_if_sold_now numeric(18,2),
             approx boolean not null default false)"""
    )
    execute_values(
        cur,
        """insert into wealth.lots
           (client_id, scheme_id, fund_name, folio, status, buy_date, buy_type, buy_txn_id,
            units, unit_cost, unit_basis, gf_applied, sell_date, sell_type, sell_txn_id,
            sell_price, realized_gain, holding_days, tax_bucket, nav_now, unrealized_gain,
            tax_if_sold_now, approx)
           values %s""",
        out_rows,
        page_size=2000,
    )
    cur.execute("create index on wealth.lots (client_id, status)")
    cur.execute("create index on wealth.lots (scheme_id)")
    cur.execute("revoke all on wealth.lots from anon, authenticated")
    conn.commit()

    cur.execute(
        """select status, count(*), sum(units), sum(realized_gain), sum(unrealized_gain),
                  sum(tax_if_sold_now) from wealth.lots group by status order by status"""
    )
    for st, n, u, rg, ug, tx in cur.fetchall():
        print(
            f"{st}: {n} slices, {float(u):.0f} units, realized ₹{float(rg or 0) / 1e7:.2f} cr, "
            f"unrealized ₹{float(ug or 0) / 1e7:.2f} cr, tax-if-sold ₹{float(tx or 0) / 1e7:.2f} cr"
        )
    # self-check: open units per fund-folio == ledger's final balance_units
    cur.execute(
        """with led as (
             select client_id, fund_name, folio,
                    (array_agg(balance_units order by txn_date desc nulls last, txn_id desc))[1] bal,
                    -- pledged units leave the ledger balance but are still owned
                    coalesce(sum(units) filter (where txn_type = 'pledge'), 0)
                      - coalesce(sum(units) filter (where txn_type = 'unpledge'), 0) net_pledged
             from wealth.transactions group by 1, 2, 3
           ),
           lo as (
             select client_id, fund_name, folio, coalesce(sum(units), 0) open_units
             from wealth.lots where status = 'open' group by 1, 2, 3
           )
           select count(*) filter (
                    where abs(coalesce(lo.open_units, 0) - (led.bal + led.net_pledged)) <= 0.005) ok,
                  count(*) total
           from led left join lo using (client_id, fund_name, folio)"""
    )
    ok, total = cur.fetchone()
    print(f"lots-vs-ledger balance check: {ok}/{total} fund-folios reconcile")
    print(f"grandfathering: {n_gf_applied} slices stepped up, {n_gf_missing} pre-2018 equity slices without FMV NAV")
    if n_oversell:
        print(f"WARN {n_oversell} sells exceeded available lot units (units unaccounted)")
    conn.close()
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
