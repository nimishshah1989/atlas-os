"""Bridge wealth.schemes to the official AMFI registry (NAVAll.txt).

AMFI is the canonical scheme registry: official name + AMFI code + ISIN +
SEBI category for EVERY scheme (equity, hybrid, debt, FoF) — exactly what the
equity-only Morningstar master cannot give us. Matching uses the same
normalizer as map_schemes.py. Regular-plan rows are preferred (the client book
is 100% Regular); Growth vs IDCW follows the display-name suffix.

Usage:
    .venv/bin/python scripts/wealth/amfi_bridge.py --navall /home/ubuntu/jhaveri_data/navall.txt --apply
"""

from __future__ import annotations

import argparse
import os
import re
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(__file__))
from map_schemes import norm

SECTION_RE = re.compile(r"^Open Ended Schemes\((.+?)\)\s*$")
ROW_RE = re.compile(r"^(\d{5,7});([^;]*);([^;]*);([^;]+);[^;]*;[^;]*$")


def parse_navall(path: str):
    """Yield (amfi_code, isin, official_name, amfi_category) for open-ended rows."""
    category = None
    for raw in open(path, encoding="utf-8", errors="ignore"):
        line = raw.strip()
        m = SECTION_RE.match(line)
        if m:
            category = m.group(1)
            continue
        m = ROW_RE.match(line)
        if m and category:
            code, isin1, isin2, name = m.groups()
            isin = isin1.strip() if isin1.strip() not in ("", "-") else isin2.strip()
            yield code, (isin if isin not in ("", "-") else None), name.strip(), category


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--navall", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    # index AMFI rows by normalized core name
    amfi: dict[str, list] = {}
    n_rows = 0
    for code, isin, name, cat in parse_navall(args.navall):
        n_rows += 1
        amfi.setdefault(norm(name), []).append((code, isin, name, cat))
    print(f"AMFI registry: {n_rows} open-ended rows, {len(amfi)} distinct core names")

    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("""alter table wealth.schemes
                   add column if not exists isin text,
                   add column if not exists amfi_category text,
                   add column if not exists amfi_official_name text""")
    cur.execute("""select s.scheme_id, s.display_name, s.option_type,
                          coalesce(sum(h.market_value), 0) as mv
                   from wealth.schemes s left join wealth.holdings h using (scheme_id)
                   group by 1, 2, 3""")
    schemes = cur.fetchall()

    matched_mv = total_mv = 0.0
    n_match = 0
    updates, unmatched = [], []
    for scheme_id, display, option, mv in schemes:
        mv = float(mv)
        total_mv += mv
        cands = amfi.get(norm(display))
        if not cands:
            import difflib

            close = difflib.get_close_matches(norm(display), list(amfi), n=2, cutoff=0.90)
            if close and (
                len(close) == 1
                or difflib.SequenceMatcher(None, norm(display), close[0]).ratio()
                - difflib.SequenceMatcher(None, norm(display), close[1]).ratio()
                > 0.03
            ):
                cands = amfi[close[0]]
        if not cands:
            unmatched.append((mv, display))
            continue
        want_idcw = option == "IDCW"

        def score(row, _want_idcw=want_idcw):
            _, isin, name, _ = row
            n = name.lower()
            is_direct = "direct" in n
            is_idcw = bool(re.search(r"idcw|dividend", n))
            return (not is_direct, is_idcw == _want_idcw, isin is not None)

        code, isin, name, cat = max(cands, key=score)
        updates.append((code, isin, name, cat, scheme_id))
        n_match += 1
        matched_mv += mv

    print(
        f"AMFI-matched {n_match}/{len(schemes)} schemes "
        f"({matched_mv / total_mv * 100:.1f}% of value)"
    )
    print("still unmatched, top by value:")
    for mv, name in sorted(unmatched, reverse=True)[:15]:
        print(f"  {mv / 1e7:8.2f} cr  {name}")
    if args.apply:
        cur.executemany(
            """update wealth.schemes
               set amfi_code = coalesce(amfi_code, %s), isin = %s,
                   amfi_official_name = %s, amfi_category = %s
               where scheme_id = %s""",
            updates,
        )
        conn.commit()
        print(f"applied {len(updates)}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
