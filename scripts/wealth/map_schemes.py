"""Map wealth.schemes display names to atlas_foundation.de_mf_master identities.

Jhaveri reports carry no ISIN/AMFI code, only truncated display names
("Franklin India Flexi Cap Reg-G"), so matching is by normalized name:
strip plan/option suffix tokens, apply AMC aliases, squash spaces, compare.
Share-class choice prefers Atlas-scored > has-NAV > plan/option agreement.

Usage:
    .venv/bin/python scripts/wealth/map_schemes.py [--apply]
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys

import psycopg2

# trailing plan/option tokens to strip (iteratively) from both sides
SUFFIX = {
    "reg",
    "regular",
    "dir",
    "direct",
    "g",
    "gr",
    "growth",
    "d",
    "div",
    "dividend",
    "idcw",
    "idcwq",
    "idcwm",
    "idcww",
    "idcwd",
    "idcwf",
    "idcwh",
    "idcwa",
    "t",
    "r",
    "p",
    "payout",
    "reinv",
    "reinvestment",
    "plan",
    "option",
}
# substring aliases applied after lowercasing (client-side spellings → master spellings)
ALIASES = [
    ("ppfas", "parag parikh"),
    ("sunlife", "sun life"),
    ("adity birla", "aditya birla"),
    ("&", " and "),
    ("l and t", "hsbc"),  # L&T MF absorbed by HSBC
    ("idfc", "bandhan"),  # IDFC MF renamed Bandhan
    ("fof", "fund of fund"),  # display style vs AMFI official style
]


def norm(name: str) -> str:
    s = name.lower()
    s = re.sub(r"\(.*?\)", " ", s)
    for a, b in ALIASES:
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in ("fund", "scheme", "an", "the")]
    while toks and toks[-1] in SUFFIX:
        toks.pop()
    return "".join(toks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    cur.execute("""select m.mstar_id, m.fund_name, m.amfi_code,
                          (u.mstar_id is not null) as in_universe,
                          exists (select 1 from atlas_foundation.de_mf_nav_daily n
                                  where n.mstar_id = m.mstar_id) as has_nav,
                          coalesce(m.fund_name ilike '%dir%', false) as is_direct,
                          coalesce(m.fund_name ~* 'idcw|div', false) as is_idcw
                   from atlas_foundation.de_mf_master m
                   left join atlas_foundation.atlas_universe_funds u using (mstar_id)""")
    master: dict[str, list] = {}
    for row in cur.fetchall():
        master.setdefault(norm(row[1]), []).append(row)

    cur.execute("""select s.scheme_id, s.display_name, s.plan_type, s.option_type,
                          coalesce(sum(h.market_value), 0)
                   from wealth.schemes s
                   left join wealth.holdings h using (scheme_id)
                   group by 1, 2, 3, 4""")
    schemes = cur.fetchall()
    keys = list(master)

    total_mv = matched_mv = 0.0
    n_matched = 0
    unmatched: list[tuple[float, str]] = []
    updates = []
    for scheme_id, display, plan, option, mv in schemes:
        mv = float(mv)
        total_mv += mv
        key = norm(display)
        method, conf, cands = None, None, master.get(key)
        if cands:
            method, conf = "normalized", 1.0
        else:
            close = difflib.get_close_matches(key, keys, n=2, cutoff=0.90)
            if close and (
                len(close) == 1
                or difflib.SequenceMatcher(None, key, close[0]).ratio()
                - difflib.SequenceMatcher(None, key, close[1]).ratio()
                > 0.03
            ):
                cands = master[close[0]]
                method = "fuzzy"
                conf = round(difflib.SequenceMatcher(None, key, close[0]).ratio(), 3)
        if not cands:
            unmatched.append((mv, display))
            continue
        want_direct = plan == "Direct"
        want_idcw = option == "IDCW"
        best = max(
            cands,
            key=lambda r: (r[3], r[4], r[5] == want_direct, r[6] == want_idcw, r[2] is not None),
        )
        n_matched += 1
        matched_mv += mv
        updates.append((best[0], best[2], best[1], method, conf, best[3], best[4], scheme_id))

    print(
        f"matched {n_matched}/{len(schemes)} schemes "
        f"({matched_mv / total_mv * 100:.1f}% of Rs {total_mv / 1e7:.1f} cr by value)"
    )
    print(
        f"  of matched: {sum(1 for u in updates if u[5])} in Atlas universe, "
        f"{sum(1 for u in updates if u[6])} with NAV series"
    )
    print("top unmatched by value:")
    for mv, name in sorted(unmatched, reverse=True)[:20]:
        print(f"  {mv / 1e7:8.2f} cr  {name}")
    if args.apply:
        cur.executemany(
            """update wealth.schemes set mstar_id=%s, amfi_code=%s, matched_name=%s,
               match_method=%s, match_confidence=%s, in_atlas_universe=%s, has_nav_series=%s
               where scheme_id=%s""",
            updates,
        )
        conn.commit()
        print(f"applied {len(updates)} matches")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
