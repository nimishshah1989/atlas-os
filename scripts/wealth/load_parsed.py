"""Load parsed Jhaveri valuation reports (parse_jhaveri.py output) into wealth schema.

Idempotent: clients upserted by PAN (fallback name+code), reports unique on
(client, as_on_date) — same-day duplicate files are skipped with a warning if
totals agree, loudly if they disagree. Holdings are replaced per report.

Usage:
    .venv/bin/python scripts/wealth/load_parsed.py --parsed /home/ubuntu/jhaveri_data/parsed.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

SUMMARY_FIELDS = [
    "lumpsum_purchases",
    "systematic_investments",
    "switch_ins",
    "redemptions",
    "systematic_withdrawals",
    "switch_outs",
    "dividend_payouts",
    "dividend_reinvested",
    "mv_equity",
    "mv_debt",
    "mv_hybrid",
    "mv_others",
    "mv_total",
    "overall_abs_return_pct",
    "overall_xirr_pct",
]
HOLDING_FIELDS = [
    "folio",
    "inv_since",
    "inv_days",
    "investments",
    "withdrawals",
    "dividends_reinvested",
    "dividend_payouts",
    "balance_units",
    "avg_cost",
    "cost_amount",
    "nav",
    "market_value",
    "port_weight_pct",
    "abs_return_pct",
    "xirr_pct",
]


def plan_option(display: str) -> tuple[str, str]:
    d = display.lower()
    plan = "Direct" if re.search(r"\bdir(ect)?\b", d) else "Regular"
    option = "IDCW" if re.search(r"idcw|div(idend)?\b|-d\b", d) else "Growth"
    return plan, option


def upsert_client(cur, rec: dict) -> int:
    pan = rec.get("pan")
    name = rec.get("client_name") or Path(rec["source_file"]).stem
    code = rec.get("client_code")
    if pan:
        cur.execute(
            """insert into wealth.clients (pan, client_code, full_name, family_group, email, mobile)
               values (%s,%s,%s,%s,%s,%s)
               on conflict (pan) do update set updated_at = now(),
                 email = coalesce(excluded.email, wealth.clients.email),
                 mobile = coalesce(excluded.mobile, wealth.clients.mobile)
               returning client_id""",
            (pan, code, name, rec["family_group"], rec.get("email"), rec.get("mobile")),
        )
    else:
        cur.execute(
            """insert into wealth.clients (pan, client_code, full_name, family_group, email, mobile)
               values (null,%s,%s,%s,%s,%s)
               on conflict (full_name, client_code) do update set updated_at = now()
               returning client_id""",
            (code, name, rec["family_group"], rec.get("email"), rec.get("mobile")),
        )
    return cur.fetchone()[0]


def get_scheme(cur, cache: dict, h: dict) -> int:
    key = h["fund_name"]
    if key in cache:
        return cache[key]
    plan, option = plan_option(key)
    cur.execute(
        """insert into wealth.schemes (display_name, asset_class, sub_category, plan_type, option_type)
           values (%s,%s,%s,%s,%s)
           on conflict (display_name) do update set display_name = excluded.display_name
           returning scheme_id, asset_class""",
        (key, h["asset_class"], h["sub_category"], plan, option),
    )
    scheme_id, existing_class = cur.fetchone()
    if existing_class != h["asset_class"]:
        print(f"  WARN scheme {key!r} seen as {existing_class} and {h['asset_class']}")
    cache[key] = scheme_id
    return scheme_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parsed", required=True)
    args = ap.parse_args()
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    data = json.load(open(args.parsed))
    bad = [d for d in data if d["errors"]]
    if bad:
        print(f"REFUSING to load: {len(bad)} files failed parse validation:")
        for d in bad:
            print(f"  {d['source_file']}: {d['errors'][:2]}")
        return 1
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(open(Path(__file__).parent / "schema.sql").read())
    scheme_cache: dict[str, int] = {}
    n_new, n_skip = 0, 0
    for rec in data:
        client_id = upsert_client(cur, rec)
        cur.execute(
            "select report_id, mv_total from wealth.client_reports where client_id=%s and as_on_date=%s",
            (client_id, rec["as_on_date"]),
        )
        existing = cur.fetchone()
        if existing:
            n_skip += 1
            if str(existing[1]) != str(rec.get("mv_total")):
                print(
                    f"  WARN duplicate report {rec['source_file']} has mv_total "
                    f"{rec.get('mv_total')} vs loaded {existing[1]} — kept first, review manually"
                )
            continue
        cur.execute(
            f"""insert into wealth.client_reports
                (client_id, as_on_date, txn_upto_date, nav_upto_date, source_file,
                 {", ".join(SUMMARY_FIELDS)})
                values (%s,%s,%s,%s,%s,{",".join(["%s"] * len(SUMMARY_FIELDS))})
                returning report_id""",
            [
                client_id,
                rec["as_on_date"],
                rec.get("txn_upto_date"),
                rec.get("nav_upto_date"),
                rec["source_file"],
            ]
            + [rec.get(f) for f in SUMMARY_FIELDS],
        )
        inserted = cur.fetchone()
        assert inserted is not None
        report_id = inserted[0]
        rows = []
        for h in rec["holdings"]:
            scheme_id = get_scheme(cur, scheme_cache, h)
            rows.append([report_id, client_id, scheme_id] + [h.get(f) for f in HOLDING_FIELDS])
        if rows:
            execute_values(
                cur,
                f"""insert into wealth.holdings
                    (report_id, client_id, scheme_id, {", ".join(HOLDING_FIELDS)}) values %s""",
                rows,
            )
        n_new += 1
    conn.commit()
    cur.execute("""select (select count(*) from wealth.clients),
                          (select count(*) from wealth.client_reports),
                          (select count(*) from wealth.holdings),
                          (select count(*) from wealth.schemes),
                          (select sum(mv_total) from wealth.client_reports)""")
    stats = cur.fetchone()
    assert stats is not None
    c, r, h, s, mv = stats
    print(f"loaded {n_new} reports ({n_skip} duplicates skipped)")
    print(
        f"DB now: {c} clients, {r} reports, {h} holdings, {s} schemes, total MV Rs {float(mv) / 1e7:.1f} cr"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
