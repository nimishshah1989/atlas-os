#!/usr/bin/env python3
"""Atlas-owned Morningstar Fund-Master ingestion → foundation_staging (single-schema).

Step 1b of the data consolidation. Replaces the dead external data-engine pull for fund
master metadata (de_mf_master was stuck at 2026-05-05; atlas_universe_funds AUM stuck at
2026-03-31). The MASTER service exposes the whole MF universe in ONE ~4MB call:

    GET /v2/service/mf/{MSTAR_MASTER_SERVICE}/universeid/{MSTAR_MASTER_UNIVERSE}?accesscode=

(the HOLDINGS service's universe call is >130MB and times out — that one must stay per-fund;
see ingest_mf_holdings.py.) This writes DIRECTLY into foundation_staging — no legacy
raw-schema hop, no consolidate mirror.

It refreshes two tables:
  * de_mf_master       — UPSERT every fund's metadata by mstar_id (preserves amc_name, which
                         the master feed does not carry).
  * atlas_universe_funds — UPDATE the curated universe's AUM/category in place by mstar_id.
                         AUM is stored in TRUE ₹ crore (= fund size in ₹ / 1e7).

Config from env (defaults = the configured master service/universe):
  MSTAR_ACCESSCODE · MSTAR_MASTER_SERVICE · MSTAR_MASTER_UNIVERSE · ATLAS_DB_URL

Run:  python ingest_fund_master.py            # refresh
      python ingest_fund_master.py --dry-run  # fetch + parse + report, no writes
"""

from __future__ import annotations

import datetime
import os
import sys
import xml.etree.ElementTree as ET

import psycopg2
import requests
from psycopg2.extras import execute_values

try:  # load repo-root .env so creds/DB resolve under cron + manual runs alike
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except Exception:
    pass

MSTAR_BASE = "https://api.morningstar.com/v2/service/mf"
SVC = os.environ.get("MSTAR_MASTER_SERVICE", "x6d9w6xxu0hmhrr4")
UNIV = os.environ.get("MSTAR_MASTER_UNIVERSE", "q3zv6b817mp4fz0f")
AC = os.environ["MSTAR_ACCESSCODE"]
# .env carries the SQLAlchemy form (postgresql+psycopg2://); psycopg2 wants plain libpq.
DB = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)

# Morningstar field tag -> our key. Tags live one level under each <data>/<api>.
RUPEES_PER_CRORE = 10_000_000  # 1 crore = 1e7


def fetch_universe(retries: int = 3) -> bytes:
    url = f"{MSTAR_BASE}/{SVC}/universeid/{UNIV}?accesscode={AC}"
    last = None
    for _a in range(retries):
        try:
            r = requests.get(url, timeout=180)
            if r.status_code == 200 and r.content.rstrip().endswith(b"</response>"):
                return r.content
            last = f"HTTP {r.status_code} ({len(r.content)}b)"
        except requests.RequestException as e:
            last = str(e)
    raise SystemExit(f"master universe fetch failed after {retries} tries: {last}")


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _date(v):
    try:
        return datetime.date.fromisoformat(v[:10]) if v else None
    except (TypeError, ValueError):
        return None


def parse_universe(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    for data in root.iter("data"):
        g = lambda t, d=data: d.find(f".//{t}").text if d.find(f".//{t}") is not None else None
        mid = g("FSCBI-MStarID")
        if not mid:
            continue
        cat = g("FSCBI-AggregatedCategoryName")
        size = _f(g("FNA-FundSizeComprehensiveMonthEnd"))
        yield {
            "mstar_id": mid,
            "isin": g("FSCBI-ISIN"),
            "amfi_code": g("FSCBI-AMFICode"),
            "fund_name": g("FSCBI-FundName"),
            "broad_category": g("FSCBI-BroadCategoryGroup"),
            "category_name": cat,
            "expense_ratio": _f(g("ARF-NetExpenseRatio")),
            "inception_date": _date(g("FSCBI-InceptionDate")),
            "benchmark": g("FB-PrimaryIndexName"),
            "is_index_fund": bool(cat and "Index" in cat),
            "aum_cr": (size / RUPEES_PER_CRORE) if size is not None else None,
            "aum_as_of": _date(g("FNA-FundSizeComprehensiveMonthEndDate")),
        }


def main() -> None:
    dry = "--dry-run" in sys.argv
    print(f"fetching master universe (svc={SVC} univ={UNIV}) ...", flush=True)
    funds = list(parse_universe(fetch_universe()))
    with_aum = sum(1 for f in funds if f["aum_cr"] is not None)
    print(f"parsed {len(funds)} funds · {with_aum} with AUM", flush=True)
    if dry:
        for f in funds[:3]:
            print("  sample:", {k: f[k] for k in ("mstar_id", "fund_name", "aum_cr", "aum_as_of")})
        print("DRY RUN — no writes")
        return

    conn = psycopg2.connect(DB)
    cur = conn.cursor()

    # Take clean ownership: de_mf_master needs a unique key on mstar_id for UPSERT.
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_de_mf_master_mstar_id "
        "ON foundation_staging.de_mf_master (mstar_id)"
    )

    # 1) de_mf_master — UPSERT mstar-provided columns; preserve amc_name (not in feed).
    master_rows = [
        (
            f["mstar_id"],
            f["amfi_code"],
            f["isin"],
            f["fund_name"],
            f["category_name"],
            f["broad_category"],
            f["is_index_fund"],
            f["inception_date"],
            f["benchmark"],
            f["expense_ratio"],
        )
        for f in funds
    ]
    execute_values(
        cur,
        "INSERT INTO foundation_staging.de_mf_master "
        "(mstar_id, amfi_code, isin, fund_name, category_name, broad_category, "
        " is_index_fund, inception_date, primary_benchmark, expense_ratio, "
        " is_active, updated_at) "
        "VALUES %s "
        "ON CONFLICT (mstar_id) DO UPDATE SET "
        "  amfi_code=EXCLUDED.amfi_code, isin=EXCLUDED.isin, fund_name=EXCLUDED.fund_name, "
        "  category_name=EXCLUDED.category_name, broad_category=EXCLUDED.broad_category, "
        "  is_index_fund=EXCLUDED.is_index_fund, inception_date=EXCLUDED.inception_date, "
        "  primary_benchmark=EXCLUDED.primary_benchmark, expense_ratio=EXCLUDED.expense_ratio, "
        "  is_active=TRUE, updated_at=now()",
        master_rows,
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,now())",
        page_size=2000,
    )
    master_n = cur.rowcount

    # 2) atlas_universe_funds — UPDATE the curated universe in place (no insert).
    #    AUM in TRUE ₹ crore. Join the feed by mstar_id via a VALUES list.
    #    (benchmark_code stays a short CODE; the master gives a full index NAME, which
    #    belongs in de_mf_master.primary_benchmark — not forced into the 32-char code col.)
    univ_rows = [
        (
            f["mstar_id"],
            f["aum_cr"],
            f["aum_as_of"],
            f["category_name"],
            f["broad_category"],
            f["inception_date"],
        )
        for f in funds
        if f["aum_cr"] is not None or f["category_name"]
    ]
    execute_values(
        cur,
        "UPDATE foundation_staging.atlas_universe_funds u SET "
        "  aum_cr = v.aum_cr, aum_as_of = v.aum_as_of, "
        "  category_name = COALESCE(v.category_name, u.category_name), "
        "  broad_category = COALESCE(v.broad_category, u.broad_category), "
        "  inception_date = COALESCE(v.inception_date, u.inception_date), "
        "  updated_at = now() "
        "FROM (VALUES %s) AS v(mstar_id, aum_cr, aum_as_of, category_name, broad_category, "
        "                      inception_date) "
        "WHERE u.mstar_id = v.mstar_id",
        univ_rows,
        template="(%s,%s::numeric,%s::date,%s,%s,%s::date)",
        page_size=2000,
    )
    univ_n = cur.rowcount

    conn.commit()
    print(
        f"DONE · de_mf_master upserted {master_n} · atlas_universe_funds updated {univ_n} "
        f"(AUM in true ₹ crore)",
        flush=True,
    )
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
