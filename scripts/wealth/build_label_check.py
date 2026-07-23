"""Does each held fund do what its name says? SEBI cap-split truth per fund.

SEBI: large = top 100 by full mcap, mid = 101-250, small = 251+. Category rules
encoded below (minimum mandates). Constituents without an equity mcap match are
'unclassified' (debt/cash/foreign/unlisted) — equity_pct counts classified equity.
Usage: .venv/bin/python scripts/wealth/build_label_check.py
"""
from __future__ import annotations
import re, sys
from engine_common import connect
from psycopg2.extras import execute_values

# (regex on wealth.schemes display/sub_category, rule fn(large, mid, small, equity) -> ok?)
CATEGORY_RULES = [
    (re.compile(r"large\s*(&|and)\s*mid", re.I), "Large & Mid Cap",
     lambda L, M, S, E: L >= 35 and M >= 35),
    (re.compile(r"large\s*cap", re.I), "Large Cap", lambda L, M, S, E: L >= 80 * E / 100),
    (re.compile(r"mid\s*cap", re.I), "Mid Cap", lambda L, M, S, E: M >= 65 * E / 100),
    (re.compile(r"small\s*cap", re.I), "Small Cap", lambda L, M, S, E: S >= 65 * E / 100),
    (re.compile(r"multi\s*cap", re.I), "Multi Cap", lambda L, M, S, E: L >= 25 and M >= 25 and S >= 25),
    (re.compile(r"flexi", re.I), "Flexi Cap", lambda L, M, S, E: E >= 65),
]


def sebi_ranks(conn):
    cur = conn.cursor()
    cur.execute(
        """select im.isin, row_number() over (order by m.market_cap_cr desc) rk
           from atlas_foundation.equity_marketcap m
           join atlas_foundation.instrument_master im using (instrument_id)
           where im.isin is not null and m.market_cap_cr is not null""")
    return {isin: ("large" if rk <= 100 else "mid" if rk <= 250 else "small")
            for isin, rk in cur.fetchall()}


def classify_fund(conn, mstar_id, ranks):
    cur = conn.cursor()
    cur.execute(
        """select isin, sum(weight_pct) from atlas_foundation.de_mf_holdings h
           where mstar_id = %s
             and as_of_date = (select max(as_of_date) from atlas_foundation.de_mf_holdings
                               where mstar_id = %s)
             and isin is not null group by 1""", (mstar_id, mstar_id))
    L = M = S = U = 0.0
    for isin, w in cur.fetchall():
        if w is None:
            continue
        w = float(w)
        b = ranks.get(isin)
        if b == "large": L += w
        elif b == "mid": M += w
        elif b == "small": S += w
        else: U += w
    return dict(large_pct=round(L, 2), mid_pct=round(M, 2), small_pct=round(S, 2),
                unclassified_pct=round(U, 2), equity_pct=round(L + M + S, 2))


def main() -> int:
    conn = connect(); cur = conn.cursor()
    ranks = sebi_ranks(conn)
    cur.execute("""select distinct s.scheme_id, s.mstar_id, s.display_name, s.sub_category
                   from wealth.schemes s join wealth.holdings h using (scheme_id)
                   where s.mstar_id is not null""")
    rows = []
    for sid, mid, disp, sub in cur.fetchall():
        c = classify_fund(conn, mid, ranks)
        cat, verdict, detail = None, "no_data", ""
        if c["equity_pct"] + c["unclassified_pct"] > 0:
            name = f"{disp} {sub or ''}"
            for rx, label, rule in CATEGORY_RULES:
                if rx.search(name):
                    cat = label
                    ok = rule(c["large_pct"], c["mid_pct"], c["small_pct"], c["equity_pct"])
                    verdict = "ok" if ok else "mismatch"
                    detail = (f"label {label}: large {c['large_pct']}% mid {c['mid_pct']}% "
                              f"small {c['small_pct']}% (unclassified {c['unclassified_pct']}%)")
                    break
            else:
                cat, verdict = "Other", "ok"  # no cap mandate to check
        rows.append((sid, mid, cat, c["equity_pct"], c["large_pct"], c["mid_pct"],
                     c["small_pct"], c["unclassified_pct"], verdict, detail))
    cur.execute("drop table if exists wealth.fund_label_check")
    cur.execute("""create table wealth.fund_label_check (
        scheme_id bigint primary key, mstar_id text, category text,
        equity_pct numeric(6,2), large_pct numeric(6,2), mid_pct numeric(6,2),
        small_pct numeric(6,2), unclassified_pct numeric(6,2), verdict text, detail text)""")
    execute_values(cur, "insert into wealth.fund_label_check values %s", rows)
    cur.execute("revoke all on wealth.fund_label_check from anon, authenticated")
    conn.commit()
    n_bad = sum(1 for r in rows if r[8] == "mismatch")
    print(f"label check: {len(rows)} held funds, {n_bad} mismatch their label")
    return 0


if __name__ == "__main__":
    sys.exit(main())
