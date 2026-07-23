"""Per-client fund-overlap: pairwise overlap, true stock exposure, effective bets.

overlap(A,B) = sum over shared ISINs of min(weight_A, weight_B) — the standard
'common portfolio' measure. eff_bets = 1 / sum(w_i^2) (inverse Herfindahl) over the
client's look-through stock weights.
Usage: .venv/bin/python scripts/wealth/build_overlap.py
"""
from __future__ import annotations
import sys
from collections import defaultdict
from engine_common import connect
from psycopg2.extras import execute_values


def latest_fund_weights(conn):
    cur = conn.cursor()
    cur.execute(
        """select h.mstar_id, h.isin, max(h.holding_name), sum(h.weight_pct)
           from atlas_foundation.de_mf_holdings h
           join (select mstar_id, max(as_of_date) d from atlas_foundation.de_mf_holdings
                 group by 1) l on l.mstar_id = h.mstar_id and l.d = h.as_of_date
           where h.isin is not null and h.weight_pct > 0
           group by 1, 2"""
    )
    out: dict = defaultdict(dict)
    for mid, isin, name, w in cur.fetchall():
        out[mid][isin] = (name, float(w))
    return out


def pairwise_overlap(wa: dict, wb: dict) -> float:
    return round(sum(min(wa[i][1], wb[i][1]) for i in wa.keys() & wb.keys()), 2)


def main() -> int:
    conn = connect(); cur = conn.cursor()
    fw = latest_fund_weights(conn)
    cur.execute(
        """select h.client_id, h.scheme_id, s.mstar_id, h.market_value::float
           from wealth.holdings h join wealth.schemes s using (scheme_id)
           where h.market_value > 0 and s.mstar_id is not null"""
    )
    rows = cur.fetchall()
    by_client = defaultdict(list)
    for cid, sid, mid, mv in rows:
        if mid in fw:
            by_client[cid].append((sid, mid, mv))
    o_rows, p_rows = [], []
    for cid, funds in by_client.items():
        stock = defaultdict(float); names = {}
        total_mv = sum(mv for _, _, mv in funds)
        for _, mid, mv in funds:
            for isin, (name, w) in fw[mid].items():
                stock[isin] += mv * w / 100.0
                names[isin] = name
        if not stock or total_mv <= 0:
            continue
        wts = {i: v / total_mv for i, v in stock.items()}
        herf = sum(w * w for w in wts.values())
        eff = round(1.0 / herf, 2) if herf > 0 else None
        top = sorted(stock.items(), key=lambda kv: -kv[1])
        top10 = round(sum(v for _, v in top[:10]) / total_mv, 3)
        o_rows.append((cid, eff, top[0][0], names[top[0][0]][:80], round(top[0][1]),
                       top10, len(funds), len(stock)))
        for i in range(len(funds)):
            for j in range(i + 1, len(funds)):
                ov = pairwise_overlap(fw[funds[i][1]], fw[funds[j][1]])
                if ov >= 20:  # store meaningful pairs only
                    p_rows.append((cid, funds[i][0], funds[j][0], ov))
    cur.execute("drop table if exists wealth.client_overlap")
    cur.execute("""create table wealth.client_overlap (
        client_id bigint primary key, eff_bets numeric(8,2), top_stock_isin text,
        top_stock_name text, top_stock_rs numeric(18,0), top10_share numeric(6,3),
        n_funds int, n_stocks int)""")
    execute_values(cur, "insert into wealth.client_overlap values %s", o_rows)
    cur.execute("drop table if exists wealth.client_fund_overlap")
    cur.execute("""create table wealth.client_fund_overlap (
        client_id bigint, scheme_a bigint, scheme_b bigint, overlap_pct numeric(6,2))""")
    execute_values(cur, "insert into wealth.client_fund_overlap values %s", p_rows, page_size=2000)
    for t in ("client_overlap", "client_fund_overlap"):
        cur.execute(f"revoke all on wealth.{t} from anon, authenticated")
    conn.commit()
    print(f"overlap: {len(o_rows)} clients, {len(p_rows)} heavy pairs (>=20%), "
          f"median eff_bets {sorted(r[1] for r in o_rows if r[1])[len(o_rows)//2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
