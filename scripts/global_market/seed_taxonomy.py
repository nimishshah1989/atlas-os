#!/usr/bin/env python3
"""Seed ``atlas_global.taxonomy_sector`` / ``taxonomy_geo`` / ``taxonomy_role`` from
``docs/global/taxonomy.md`` (FM-reviewed, versioned).

    python scripts/global_market/seed_taxonomy.py --dry-run   # print the rows, write nothing
    python scripts/global_market/seed_taxonomy.py             # ON CONFLICT DO NOTHING

This is the ALLOWLIST, not a hint. ``classify/llm.py`` builds its output schema from these
rows at runtime, so the model cannot return a category that is not here — the constraint is
enforced by the schema rather than by asking the model nicely. That makes an omission a fund
with nowhere to go, which is why the document is reviewed before this runs.

Every category was counted against the 5,656 real active ETF names rather than chosen from a
mental model of the US market; ``docs/global/taxonomy.md`` carries the method, the counts and
what they overturned in the plan. Rows are seeded only where funds exist to fill them: an
empty category is one nobody can use and one the model will reach for anyway.

WHY THERE ARE NO COUNTRY ROWS YET. ``taxonomy_geo`` rows of kind ``country`` reference
``atlas_global.country``, and that table is deliberately still empty. ISO-3166 is a published
standard, so transcribing it from memory would risk a wrong code for no reason, and the
obvious package for it is LGPL, which is a licence question for a commercial adviser product
rather than a decision to make silently in a seed script. Neither is the real reason to wait,
though: **country rows arrive with holdings.** N-PORT states each holding's
``investment_country`` as real feed data, and MSCI's developed/emerging/frontier split — which
is proprietary and must never be invented — can be MEASURED from the constituents of MSCI's
own index ETFs. Until then the region rows below carry every roll-up the board needs, and no
fund can be proven single-country without holdings anyway.
"""

from __future__ import annotations

import argparse
from typing import Any

import _gdb
import psycopg2
from psycopg2.extras import execute_values

M = _gdb.M
TAXONOMY_VERSION = 1

# ── level 1: GICS 11, with the fund counts measured over the real universe ──────────────
# Unchanged from the standard on purpose: the SPY holdings workbook already labels your
# stocks with these, so ETF sectors and stock sectors agree by construction rather than by a
# mapping someone has to maintain.
SECTORS_L1: list[tuple[str, str, str]] = [
    ("energy", "10", "Energy"),
    ("materials", "15", "Materials"),
    ("industrials", "20", "Industrials"),
    ("consumer_discretionary", "25", "Consumer Discretionary"),
    ("consumer_staples", "30", "Consumer Staples"),
    ("health_care", "35", "Health Care"),
    ("financials", "40", "Financials"),
    ("information_technology", "45", "Information Technology"),
    ("communication_services", "50", "Communication Services"),
    ("utilities", "55", "Utilities"),
    ("real_estate", "60", "Real Estate"),
]

# ── level 2: sub-sector — the nuance India's 21 sectors could not carry ─────────────────
# Seeded only where the real universe has funds. The plan named four of these as examples
# and all four survived contact with the data.
SECTORS_L2: list[tuple[str, str, str]] = [
    ("energy_integrated", "energy", "Integrated Oil & Gas"),
    ("energy_exploration_production", "energy", "Exploration & Production"),
    ("energy_midstream_transmission", "energy", "Midstream & Pipelines"),
    ("energy_services_equipment", "energy", "Oilfield Services & Equipment"),
    ("energy_renewable_solar", "energy", "Renewable & Solar"),
    ("energy_nuclear_uranium", "energy", "Nuclear & Uranium"),
    ("materials_metals_mining", "materials", "Metals & Mining"),
    ("materials_precious_metals", "materials", "Precious Metals Miners"),
    ("materials_chemicals", "materials", "Chemicals"),
    ("industrials_aerospace_defence", "industrials", "Aerospace & Defence"),
    ("industrials_transport_logistics", "industrials", "Transport & Logistics"),
    ("industrials_machinery_construction", "industrials", "Machinery & Construction"),
    ("consumer_discretionary_retail", "consumer_discretionary", "Retail"),
    ("consumer_discretionary_homebuild", "consumer_discretionary", "Homebuilders"),
    ("consumer_discretionary_leisure_travel", "consumer_discretionary", "Leisure & Travel"),
    ("consumer_staples_food_beverage", "consumer_staples", "Food & Beverage"),
    ("consumer_staples_agriculture", "consumer_staples", "Agriculture"),
    ("health_care_biotech", "health_care", "Biotechnology"),
    ("health_care_pharma", "health_care", "Pharmaceuticals"),
    ("health_care_devices_services", "health_care", "Devices & Services"),
    ("financials_banks", "financials", "Banks"),
    ("financials_insurance", "financials", "Insurance"),
    ("financials_capital_markets", "financials", "Capital Markets & Exchanges"),
    ("information_technology_semiconductors", "information_technology", "Semiconductors"),
    ("information_technology_software", "information_technology", "Software"),
    ("information_technology_hardware", "information_technology", "Hardware & Equipment"),
    (
        "communication_services_media_entertainment",
        "communication_services",
        "Media & Entertainment",
    ),
    ("communication_services_telecom", "communication_services", "Telecommunications"),
    ("utilities_grid", "utilities", "Grid & Transmission"),
    ("utilities_power_generation", "utilities", "Power Generation"),
    ("real_estate_equity_reits", "real_estate", "Equity REITs"),
    ("real_estate_mortgage_reits", "real_estate", "Mortgage REITs"),
    ("real_estate_data_centres", "real_estate", "Data Centres & Towers"),
]

# ── level 3: theme ─────────────────────────────────────────────────────────────────────
# Measured fund counts in the comment. NINE of these sixteen sit below
# `peer_group_min_members` (8), so a fund scored inside them would be ranked against too few
# competitors to mean anything and the scorer falls back to the parent sector. They are
# seeded anyway so the board can browse and filter by them — see taxonomy.md, open question 3.
THEMES: list[tuple[str, str, str, int]] = [
    ("ai", "information_technology", "Artificial Intelligence", 64),
    ("infrastructure", "industrials", "Infrastructure", 51),
    ("space_defence", "industrials", "Space & Defence", 37),
    ("semiconductors", "information_technology", "Semiconductors", 34),
    ("genomics", "health_care", "Genomics", 21),
    ("cybersecurity", "information_technology", "Cybersecurity", 16),
    ("robotics", "industrials", "Robotics & Automation", 14),
    ("ev_battery", "consumer_discretionary", "Electric Vehicles & Batteries", 13),
    ("nuclear_uranium", "energy", "Nuclear & Uranium", 12),
    ("clean_energy", "energy", "Clean Energy", 10),
    ("quantum", "information_technology", "Quantum Computing", 8),
    ("cloud", "information_technology", "Cloud Computing", 6),
    ("fintech", "financials", "Financial Technology", 6),
    ("water", "utilities", "Water", 6),
    ("gaming_esports", "communication_services", "Gaming & Esports", 6),
    ("cannabis", "health_care", "Cannabis", 4),
]

# ── geography: regions and global only (see the module docstring on countries) ──────────
REGIONS: list[tuple[str, str, str]] = [
    ("north_america", "north_america", "North America"),
    ("europe", "europe", "Europe"),
    ("developed_europe", "europe", "Developed Europe"),
    ("asia_pacific", "asia_pacific", "Asia Pacific"),
    ("asia_ex_japan", "asia_pacific", "Asia ex-Japan"),
    ("latin_america", "latin_america", "Latin America"),
    ("middle_east_africa", "middle_east_africa", "Middle East & Africa"),
    ("emerging_markets", "emerging_markets", "Emerging Markets"),
    ("developed_markets", "developed_markets", "Developed Markets"),
    ("frontier_markets", "frontier_markets", "Frontier Markets"),
    ("world_ex_us", "world_ex_us", "World ex-US"),
]

# ── role: fixed by the schema's CHECK, so this table can only ever hold these four ──────
ROLES: list[tuple[str, str, str]] = [
    ("pure_play", "Pure play", "Direct exposure to the theme or sector itself"),
    (
        "picks_and_shovels",
        "Picks and shovels",
        "Supplies the theme rather than being it: equipment, infrastructure, inputs",
    ),
    ("diversified", "Diversified", "Spread across sectors or themes with no single bet"),
    ("not_applicable", "Not applicable", "Not an equity sector or theme bet"),
]

SECTOR_SQL = f"""
insert into {M}.taxonomy_sector (id, level, parent_id, name, gics_code, description, version)
values %s on conflict (id) do nothing
"""
GEO_SQL = f"""
insert into {M}.taxonomy_geo (id, kind, iso2, region, name, version)
values %s on conflict (id) do nothing
"""
ROLE_SQL = f"""
insert into {M}.taxonomy_role (id, name, description) values %s on conflict (id) do nothing
"""


def _one(cur: Any, sql: str) -> int:
    """The single scalar a ``count()`` returns, or a loud failure if there is no row."""
    cur.execute(sql)
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"expected one row from: {sql}")
    return int(row[0])


def sector_rows() -> list[tuple[object, ...]]:
    """Level 1, then 2, then 3 — parents before children, because ``parent_id`` is a FK to
    this same table and an out-of-order insert fails rather than silently reordering."""
    rows: list[tuple[object, ...]] = [
        (sid, 1, None, name, gics, None, TAXONOMY_VERSION) for sid, gics, name in SECTORS_L1
    ]
    rows += [
        (sid, 2, parent, name, None, None, TAXONOMY_VERSION) for sid, parent, name in SECTORS_L2
    ]
    rows += [
        (
            tid,
            3,
            parent,
            name,
            None,
            f"{funds} funds in the 2026-09-07 universe"
            + (
                ""
                if funds >= 8
                else "; below peer_group_min_members, scores fall back to the parent sector"
            ),
            TAXONOMY_VERSION,
        )
        for tid, parent, name, funds in THEMES
    ]
    return rows


def geo_rows() -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = [
        (gid, "region", None, region, name, TAXONOMY_VERSION) for gid, region, name in REGIONS
    ]
    rows.append(("global", "global", None, None, "Global", TAXONOMY_VERSION))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="print the rows; write nothing")
    args = ap.parse_args(argv)

    sectors, geos = sector_rows(), geo_rows()
    print(f"taxonomy v{TAXONOMY_VERSION} — from docs/global/taxonomy.md")
    print(
        f"  taxonomy_sector {len(sectors):3d} rows "
        f"(L1 {len(SECTORS_L1)}, L2 {len(SECTORS_L2)}, L3 {len(THEMES)})"
    )
    print(
        f"  taxonomy_geo    {len(geos):3d} rows (regions {len(REGIONS)} + global; countries await holdings)"
    )
    print(f"  taxonomy_role   {len(ROLES):3d} rows")
    if args.dry_run:
        print(f"\n{'id':46s} {'lvl':>3s}  parent")
        for r in sectors:
            print(f"{r[0]!s:46s} {r[1]:3d}  {r[2] or ''}")
        print("\n--dry-run: nothing written")
        return 0

    conn = psycopg2.connect(_gdb.psycopg2_url())
    try:
        with conn, conn.cursor() as cur:
            # Sectors go in ONE execute_values in level order: parents must exist before the
            # children that reference them, and a single statement keeps that ordering.
            execute_values(cur, SECTOR_SQL, sectors, page_size=200)
            execute_values(cur, GEO_SQL, geos, page_size=200)
            execute_values(cur, ROLE_SQL, ROLES, page_size=200)
            cur.execute(f"select level, count(*) from {M}.taxonomy_sector group by 1 order by 1")
            by_level = dict(cur.fetchall())
            # fetchone() is Optional; a count() always returns a row, so None here would
            # mean the query itself changed and an honest failure beats a TypeError later.
            n_geo = _one(cur, f"select count(*) from {M}.taxonomy_geo")
            n_role = _one(cur, f"select count(*) from {M}.taxonomy_role")
    finally:
        conn.close()

    print(
        f"\n  in the table now: sectors by level {by_level}, geo {n_geo}, roles {n_role}"
        "\n  (existing rows are left untouched — re-running is safe and changes nothing)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
