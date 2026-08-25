#!/usr/bin/env python3
"""Add the Regular/Growth funds of a broad category to atlas_universe_funds.

WHY: `atlas_universe_funds` is the curated set every fund job reads — ingest_nav,
compute_fund_technicals and ingest_mf_holdings all target it, NOT de_mf_master. So
widening the Morningstar universe (which fills de_mf_master) is only half the job:
until a fund lands here it gets no NAV, no technicals and no rank.

It was populated by hand and had no writer, which is why adding hybrid funds needed
this script.

PLAN/OPTION COMES FROM AMFI, NOT FROM THE FUND NAME. Morningstar's `fund_name` does
not reliably carry the plan or option, and inferring them from name substrings is
guesswork — "Growth" appears in plenty of scheme names that are not the Growth option.
AMFI's NAVAll.txt carries Plan and Option as their own fields, keyed by the same
amfi_code de_mf_master stores. That is the real source and this reads it.

    python extend_fund_universe.py --broad Allocation "Alternative Strategies" --dry-run
    python extend_fund_universe.py --broad Allocation "Alternative Strategies"
"""

from __future__ import annotations

import argparse
import datetime as dt
from collections import Counter

import _db
import pandas as pd
import requests

M = "atlas_foundation"
AMFI_NAVALL = "https://portal.amfiindia.com/spages/NAVAll.txt"

# AMFI NAVAll row: code;isin;isin2;scheme_name;plan;option;nav;date
_MIN_FIELDS = 8


def amfi_regular_growth() -> set[int]:
    """AMFI scheme codes whose plan is Regular and option is Growth.

    Excludes Direct plans and every IDCW/dividend variant, per the FM scope
    (2026-08-24): Regular plan, Growth option, no IDCW, no debt, no overseas.
    """
    r = requests.get(AMFI_NAVALL, timeout=120)
    r.raise_for_status()
    codes: set[int] = set()
    for line in r.text.splitlines():
        parts = line.strip().split(";")
        if len(parts) < _MIN_FIELDS or not parts[0].strip().isdigit():
            continue
        plan, option = parts[4].strip().lower(), parts[5].strip().lower()
        if "direct" in plan:
            continue
        if "idcw" in option or "dividend" in option:
            continue
        if "growth" not in option:
            continue
        codes.add(int(parts[0].strip()))
    return codes


def candidates(broad: list[str], amfi_codes: set[int]):
    """Master funds in the requested broad categories that AMFI marks Regular/Growth
    and that are not already in the universe."""
    df = _db.read_df(
        f"""SELECT m.mstar_id, m.fund_name, m.amc_name, m.broad_category,
                   m.category_name, m.inception_date, m.amfi_code
            FROM {M}.de_mf_master m
            LEFT JOIN {M}.atlas_universe_funds u ON u.mstar_id = m.mstar_id
            WHERE m.is_active AND u.mstar_id IS NULL
              AND m.amfi_code IS NOT NULL
              AND m.broad_category = ANY(:b)""",
        {"b": broad},
    )
    if df.empty:
        return df
    code = pd.Series(df["amfi_code"]).astype(str)
    df = df.loc[code.str.isdigit()]
    keep = pd.Series(df["amfi_code"]).astype(int).isin(list(amfi_codes))
    return pd.DataFrame(df.loc[keep]).copy()


def run(broad: list[str], dry_run: bool) -> dict:
    amfi = amfi_regular_growth()
    print(f"  AMFI Regular+Growth scheme codes: {len(amfi):,}")

    before = int(_db.scalar(f"SELECT count(*) FROM {M}.atlas_universe_funds") or 0)
    df = candidates(broad, amfi)
    print(f"  universe before: {before}  ·  new candidates: {len(df)}")
    if df.empty:
        return {"before": before, "added": 0, "after": before}

    by_cat = Counter(pd.Series(df["category_name"]).tolist())
    for cat, n in by_cat.most_common():
        print(f"    {n:4d}  {cat}")

    if dry_run:
        print("  DRY RUN — no write.")
        return {"before": before, "added": 0, "after": before, "dry_run": True}

    ins = pd.DataFrame(
        {
            "mstar_id": pd.Series(df["mstar_id"]).to_numpy(),
            "scheme_name": pd.Series(df["fund_name"]).to_numpy(),
            "amc": pd.Series(df["amc_name"]).to_numpy(),
            "broad_category": pd.Series(df["broad_category"]).to_numpy(),
            "category_name": pd.Series(df["category_name"]).to_numpy(),
            "inception_date": pd.Series(df["inception_date"]).to_numpy(),
        }
    )
    # plan_type/option_type are asserted from AMFI's own fields, not inferred from a name.
    ins["plan_type"] = "Regular"
    ins["option_type"] = "Growth"
    ins["effective_from"] = dt.date.today()
    ins["created_at"] = dt.datetime.now(dt.UTC)
    ins["updated_at"] = dt.datetime.now(dt.UTC)
    n = _db.upsert_df(f"{M}.atlas_universe_funds", ins, ["mstar_id"])

    after = int(_db.scalar(f"SELECT count(*) FROM {M}.atlas_universe_funds") or 0)
    print(f"  universe after: {after} (+{after - before})")
    return {"before": before, "added": n, "after": after}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--broad", nargs="+", required=True, help="broad_category values to add")
    ap.add_argument("--dry-run", action="store_true")
    print(run(ap.parse_args().broad, ap.parse_args().dry_run))
