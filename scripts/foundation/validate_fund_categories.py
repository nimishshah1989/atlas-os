#!/usr/bin/env python3
"""Gate for the /funds/compare category board — asserts on REAL produced data.

The board builds an equal-weighted composite per fund category and plots it against a
benchmark index. Two silent failure modes make it lie rather than break, and neither shows
up in a table-level freshness check:

  1. A category's funds drop out of atlas_universe_funds. ingest_nav.py refreshes exactly
     that join, so those NAVs freeze while the rest of the board stays current — the curve
     simply ends early and reads as though the category stopped performing. This already
     happened to Index Funds, Focused Fund and Equity-ESG (361 funds).
  2. A benchmark index stops updating, or a category is added with no mapping, so the
     comparison silently falls back to a different index than the label claims.

Exit 0 iff every assertion passes. Prints PASS/FAIL per assertion.

    python validate_fund_categories.py
"""

from __future__ import annotations

import sys

import _db

MASTER = "atlas_foundation.de_mf_master"
NAV = "atlas_foundation.de_mf_nav_daily"
UNIV = "atlas_foundation.atlas_universe_funds"
PRICES = "atlas_foundation.index_prices"

# Mirrors CATEGORY_INDEX in frontend/src/lib/queries/fund_category_curve.ts. Kept here
# deliberately: this gate must fail when the two drift, which is the whole point of an
# independent check. It is a reference mapping, not a tuned threshold, so it does not
# belong in atlas_thresholds.
CATEGORY_INDEX = {
    "India Fund Index Funds": "NIFTY 500",
    "India Fund Flexi Cap": "NIFTY 500",
    "India Fund ELSS (Tax Savings)": "NIFTY 500",
    "India Fund Focused Fund": "NIFTY 500",
    "India Fund Large-Cap": "NIFTY 100",
    "India Fund Large & Mid-Cap": "NIFTY LARGEMID250",
    "India Fund Mid-Cap": "NIFTY MIDCAP 150",
    "India Fund Small-Cap": "NIFTY SMLCAP 250",
    "India Fund Multi-Cap": "NIFTY500 MULTICAP",
    "India Fund Value": "NIFTY500 VALUE 50",
    "India Fund Equity - Consumption": "NIFTY CONSUMPTION",
    "India Fund Equity - Infrastructure": "NIFTY INFRA",
    "India Fund Equity - ESG": "NIFTY100 ESG",
    "India Fund Sector - Financial Services": "NIFTY FIN SERVICE",
    "India Fund Sector - Healthcare": "NIFTY HEALTHCARE",
    "India Fund Sector - Technology": "NIFTY IT",
    "India Fund Sector - Energy": "NIFTY ENERGY",
    "India Fund Sector - FMCG": "NIFTY FMCG",
}

# NAVs publish a day or two behind the index; beyond that the feed is broken, not lagging.
MAX_NAV_LAG_DAYS = 4
# The board is not worth serving if the universe collapses. 592 funds on 2026-08-04.
MIN_UNIVERSE_FUNDS = 400
MIN_CATEGORIES = 12


class Gate:
    def __init__(self) -> None:
        self.fails = 0

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        print(f"  {mark} {label}{f' — {detail}' if detail else ''}")
        if not ok:
            self.fails += 1


def main() -> None:
    g = Gate()

    n_univ = int(_db.scalar(f"SELECT count(*) FROM {UNIV}") or 0)
    g.check(
        n_univ >= MIN_UNIVERSE_FUNDS,
        "curated universe populated",
        f"{n_univ} funds (floor {MIN_UNIVERSE_FUNDS})",
    )

    # Every category the board would offer, with its freshness. Universe-scoped, exactly as
    # the page queries it — validating a wider set would pass while the page sits empty.
    cats = _db.read_df(f"""
        SELECT m.category_name AS cat, count(DISTINCT m.mstar_id) AS n, max(l.last_d) AS last_d
        FROM {MASTER} m
        JOIN {UNIV} u ON u.mstar_id = m.mstar_id
        JOIN (SELECT mstar_id, max(nav_date) AS last_d FROM {NAV} GROUP BY mstar_id) l
          ON l.mstar_id = m.mstar_id
        WHERE m.category_name IS NOT NULL
        GROUP BY m.category_name
        ORDER BY m.category_name
    """)
    g.check(
        len(cats) >= MIN_CATEGORIES, "categories offered", f"{len(cats)} (floor {MIN_CATEGORIES})"
    )

    idx_latest = _db.scalar(f"SELECT max(date) FROM {PRICES}")
    if idx_latest is None:
        g.check(False, "index_prices has data", "table is empty")
        print("\n❌ 1 assertion(s) FAILED")
        sys.exit(1)

    stale = [
        (c, d)
        for c, d in zip(cats["cat"], cats["last_d"], strict=True)
        if (idx_latest - d).days > MAX_NAV_LAG_DAYS
    ]
    g.check(
        not stale,
        f"every offered category refreshes (NAV within {MAX_NAV_LAG_DAYS}d of index)",
        "all current" if not stale else "; ".join(f"{c} stuck at {d}" for c, d in stale[:4]),
    )

    names = list(cats["cat"])
    unmapped = [c for c in names if c not in CATEGORY_INDEX]
    g.check(
        not unmapped,
        "every offered category has a benchmark mapping",
        "all mapped" if not unmapped else ", ".join(unmapped),
    )

    # A mapping pointing at an index we do not carry, or one that has stopped updating, makes
    # the comparison quietly wrong rather than absent.
    codes = sorted({CATEGORY_INDEX[c] for c in names if c in CATEGORY_INDEX})
    have_df = _db.read_df(
        f"SELECT index_code, max(date) AS last_d FROM {PRICES} "
        "WHERE index_code = ANY(:codes) GROUP BY index_code",
        {"codes": codes},
    )
    have = dict(zip(have_df["index_code"], have_df["last_d"], strict=True))
    missing = [c for c in codes if c not in have]
    g.check(
        not missing,
        "every mapped benchmark exists in index_prices",
        f"{len(codes)} codes" if not missing else ", ".join(missing),
    )

    lagging = [(c, d) for c, d in have.items() if (idx_latest - d).days > MAX_NAV_LAG_DAYS]
    g.check(
        not lagging,
        "every mapped benchmark is current",
        "all current" if not lagging else "; ".join(f"{c} stuck at {d}" for c, d in lagging[:4]),
    )

    print(f"\n{'✅ ALL GREEN' if g.fails == 0 else f'❌ {g.fails} assertion(s) FAILED'}")
    sys.exit(0 if g.fails == 0 else 1)


if __name__ == "__main__":
    main()
