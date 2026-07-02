#!/usr/bin/env python3
"""Atlas-owned Morningstar Fund-Holdings ingestion → atlas_foundation.de_mf_holdings.

Replaces the dead external data-engine pull (holdings were stuck at 2026-05-04 — the
engine stopped fetching them ~8 weeks ago). Pulls Fund Holdings Detail PER FUND from
Morningstar (the whole-universe call is >130MB and times out), maps each holding's ISIN
to the NSE instrument, and upserts a fresh snapshot dated with the pull date. Run WEEKLY.

Config from env (defaults = the configured holdings service):
  MSTAR_ACCESSCODE · MSTAR_HOLDINGS_SERVICE · ATLAS_DB_URL
"""

from __future__ import annotations

import datetime
import os
import time
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import requests
from psycopg2.extras import execute_values

try:  # load repo-root .env so creds/DB resolve under cron + manual runs alike
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except Exception:
    pass

MSTAR_BASE = "https://api.morningstar.com/v2/service/mf"
SVC = os.environ.get("MSTAR_HOLDINGS_SERVICE", "fq9mxhk7xeb20f3b")
AC = os.environ["MSTAR_ACCESSCODE"]
DB = os.environ["ATLAS_DB_URL"]
WORKERS = int(os.environ.get("MSTAR_WORKERS", "6"))
CACHE = os.environ.get("MSTAR_CACHE_DIR")  # optional disk cache (dev iteration; cron leaves unset)


def fetch_one(mstar_id: str, retries: int = 3) -> bytes | None:
    cp = os.path.join(CACHE, f"{mstar_id}.xml") if CACHE else None
    if cp and os.path.exists(cp):
        b = open(cp, "rb").read()
        if b.rstrip().endswith(b"</response>"):
            return b
    url = f"{MSTAR_BASE}/{SVC}/mstarid/{mstar_id}?accesscode={AC}"
    for a in range(retries):
        try:
            r = requests.get(url, timeout=40)
            if r.status_code == 200 and r.content.rstrip().endswith(b"</response>"):
                if cp:
                    open(cp, "wb").write(r.content)
                return r.content
        except requests.RequestException:
            pass
        time.sleep(1.5 * (a + 1))
    return None


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_fund(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    data = root.find("data")
    if data is None:
        return
    fund = data.get("_id")
    for hd in root.iter("HoldingDetail"):
        g = lambda t, hd=hd: hd.find(t).text if hd.find(t) is not None else None
        yield {
            "mstar_id": fund,
            "isin": g("ISIN"),
            "holding_name": g("Name"),
            "weight_pct": _f(g("Weighting")),
            "shares_held": _i(g("NumberOfShare")),
            "market_value": _f(g("MarketValue")),
            "sector_code": g("SectorId"),
        }


def main() -> None:
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT isin, instrument_id FROM atlas_foundation.instrument_master "
        "WHERE isin IS NOT NULL AND asset_class='stock'"
    )
    isin_map = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute(
        "SELECT DISTINCT mstar_id FROM atlas_foundation.atlas_universe_funds "
        "WHERE mstar_id IS NOT NULL"
    )
    funds = [r[0] for r in cur.fetchall()]
    print(f"fetching holdings for {len(funds)} funds @ {WORKERS} workers ...", flush=True)

    today = datetime.date.today()
    rows, ok, miss = [], 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, f): f for f in funds}
        for i, fut in enumerate(as_completed(futs), 1):
            xml = fut.result()
            if not xml:
                miss += 1
                continue
            ok += 1
            try:
                for h in parse_fund(xml):
                    if not h["isin"]:
                        continue
                    iid = isin_map.get(h["isin"])
                    rows.append(
                        (
                            str(uuid.uuid4()),
                            h["mstar_id"],
                            today,
                            h["holding_name"],
                            h["isin"],
                            iid,
                            h["weight_pct"],
                            h["shares_held"],
                            h["market_value"],
                            h["sector_code"],
                            iid is not None,
                        )
                    )
            except ET.ParseError:
                miss += 1
            if i % 100 == 0:
                print(f"  {i}/{len(funds)} ...", flush=True)

    cur.execute("DELETE FROM atlas_foundation.de_mf_holdings WHERE as_of_date=%s", (today,))
    execute_values(
        cur,
        "INSERT INTO atlas_foundation.de_mf_holdings "
        "(id, mstar_id, as_of_date, holding_name, isin, instrument_id, weight_pct, "
        " shares_held, market_value, sector_code, is_mapped) VALUES %s",
        rows,
        page_size=5000,
    )
    conn.commit()
    mapped = sum(1 for r in rows if r[10])
    print(
        f"DONE · {ok} funds fetched ({miss} failed) · {len(rows)} holdings · as_of {today} · "
        f"mapped {mapped}/{len(rows)} ({100 * mapped // max(len(rows), 1)}%)",
        flush=True,
    )
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
