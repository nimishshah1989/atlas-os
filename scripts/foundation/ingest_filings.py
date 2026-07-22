#!/usr/bin/env python3
"""Ingest NSE corporate announcements → atlas_foundation.lens_filings.

Powers the Catalyst lens. Ported from jip-india/india_alpha/fetchers/nse_filings_fetcher.py.
Uses the same NSE-session cookie pattern as ingest_xbrl.py (proven, sync requests).
Resumable via lens_filings_state; safe to kill/restart.

Run: python ingest_filings.py [--limit N] [--redo]
"""

from __future__ import annotations

import argparse
import datetime as dt
import time

import _db
import pandas as pd
import requests
from harness import STAGING_SCHEMA

M = STAGING_SCHEMA
_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}
_API = "https://www.nseindia.com/api/corporate-announcements"

# Category classification: keyword → (bucket, priority)
_CATS = {
    "concall": ("earnings", "HIGH"),
    "analyst meet": ("earnings", "HIGH"),
    "outcome of board": ("earnings", "HIGH"),
    "financial results": ("earnings", "HIGH"),
    "investor presentation": ("earnings", "MEDIUM"),
    "annual report": ("earnings", "MEDIUM"),
    "acquisition": ("capital", "HIGH"),
    "amalgamation": ("capital", "HIGH"),
    "merger": ("capital", "HIGH"),
    "buyback": ("capital", "HIGH"),
    "credit rating": ("capital", "MEDIUM"),
    "dividend": ("capital", "MEDIUM"),
    "bonus": ("capital", "MEDIUM"),
    "split": ("capital", "MEDIUM"),
    "press release": ("capital", "MEDIUM"),
    "appointment": ("governance", "MEDIUM"),
    "cessation": ("governance", "MEDIUM"),
    "resignation": ("governance", "MEDIUM"),
    "change in director": ("governance", "MEDIUM"),
    "auditor": ("governance", "HIGH"),
    "change in auditor": ("governance", "HIGH"),
    "takeover": ("governance", "MEDIUM"),
}
# Procedural: skip
_SKIP = {
    "newspaper",
    "advertisement",
    "certificate",
    "trading window",
    "shareholders meeting",
    "annual general meeting",
    "postal ballot",
    "book closure",
    "record date",
    "listing",
    "compliance certificate",
}


def ddl() -> None:
    _db.exec_script(f"""
    create table if not exists {M}.lens_filings (
        instrument_id uuid not null, symbol text not null,
        filing_date date not null, category text,
        category_bucket text not null, signal_priority text not null,
        subject_text text, source_url text, nse_seq_id text,
        source text not null default 'NSE', ingested_at timestamptz not null default now(),
        primary key (instrument_id, nse_seq_id)
    );
    create table if not exists {M}.lens_filings_state (
        instrument_id uuid primary key, symbol text not null,
        status text not null, filings integer, error text,
        updated_at timestamptz not null default now()
    );
    -- summary_text = NSE's own extracted-text précis of the attachment (attchmntText):
    -- the 2-3 lines of what the filing is actually about, so the FM needn't open the PDF.
    alter table {M}.lens_filings add column if not exists summary_text text;
    """)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_H)
    s.get("https://www.nseindia.com/", timeout=20)
    s.get("https://www.nseindia.com/option-chain", timeout=20)
    return s


def _parse_date(s: str) -> dt.date | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _classify(subject: str, category: str) -> tuple[str, str, str]:
    """Return (matched_category, bucket, priority) or None for skip."""
    combined = f"{subject} {category}".lower()
    for kw in _SKIP:
        if kw in combined:
            return None
    for kw in sorted(_CATS, key=len, reverse=True):
        if kw in combined:
            b, p = _CATS[kw]
            return kw, b, p
    return "other", "governance", "LOW"


def ingest_symbol(s: requests.Session, iid: str, symbol: str) -> int:
    r = s.get(_API, params={"index": "equities", "symbol": symbol}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = data.get("data", data.get("announcements", []))
    rows = []
    for rec in data:
        subject = (rec.get("desc") or rec.get("subject") or "")[:2000]
        cat_raw = rec.get("smIndustry") or rec.get("category") or ""
        cl = _classify(subject, cat_raw)
        if cl is None:
            continue
        cat, bucket, prio = cl
        date_str = rec.get("an_dt") or rec.get("dt") or ""
        fd = _parse_date(date_str)
        if not fd:
            continue
        seq = str(rec.get("seq_id") or rec.get("an_dt", ""))
        if not seq:
            continue
        att = rec.get("attchmntFile") or rec.get("an_attachment") or ""
        url = (
            att
            if att.startswith("http")
            else (f"https://archives.nseindia.com/corporate/ann/{att}" if att else None)
        )
        # NSE's own extracted précis of the attachment — the substance of the filing.
        summary = (rec.get("attchmntText") or "").strip()[:2000] or None
        rows.append(
            {
                "instrument_id": iid,
                "symbol": symbol,
                "filing_date": fd,
                "category": cat,
                "category_bucket": bucket,
                "signal_priority": prio,
                "subject_text": subject,
                "summary_text": summary,
                "source_url": url,
                "nse_seq_id": seq,
            }
        )
    if not rows:
        return 0
    df = pd.DataFrame(rows).drop_duplicates(subset=["instrument_id", "nse_seq_id"], keep="last")
    return _db.upsert_df(f"{M}.lens_filings", df, ["instrument_id", "nse_seq_id"])


def targets(only_pending: bool, limit):
    df = _db.read_df(
        f"select instrument_id, symbol from {M}.instrument_master "
        "where asset_class='stock' and kite_token is not null order by symbol"
    )
    df["instrument_id"] = df["instrument_id"].astype(str)
    if only_pending:
        # Re-fetch every symbol DAILY. Skip only those successfully fetched in the
        # last 20h, which gives same-night resume (a mid-run restart doesn't redo
        # completed symbols) WITHOUT freezing the feed. 'done' is NOT terminal: the
        # upsert is idempotent on (instrument_id, nse_seq_id), so a daily re-fetch
        # simply adds any new announcements.
        #
        # Bug this fixes: the old query skipped every 'done' symbol forever, so once
        # the backfill marked ~all symbols done (~Jun-Jul 2026) the nightly cron
        # stopped ingesting new filings entirely (24 filings in Jul vs 6,267 in Jun).
        recent = _db.read_df(
            f"select instrument_id from {M}.lens_filings_state "
            "where status='done' and updated_at > now() - interval '20 hours'"
        )
        df = df[~df["instrument_id"].isin(set(recent["instrument_id"].astype(str)))]
    return df.head(limit) if limit else df


def run(only_pending=True, limit=None) -> dict:
    ddl()
    tgt = targets(only_pending, limit)
    total = len(tgt)
    done = err = ftot = 0
    s = _session()
    print(f"[filings] targets={total}", flush=True)
    for n, r in enumerate(tgt.itertuples(), 1):
        iid, sym = r.instrument_id, r.symbol
        try:
            f = ingest_symbol(s, iid, sym)
            _db.upsert_df(
                f"{M}.lens_filings_state",
                pd.DataFrame(
                    [
                        {
                            "instrument_id": iid,
                            "symbol": sym,
                            "status": "done" if f else "no_data",
                            "filings": f,
                            "error": None,
                            "updated_at": dt.datetime.now(dt.UTC),
                        }
                    ]
                ),
                ["instrument_id"],
            )
            done += 1
            ftot += f
        except Exception as e:
            msg = repr(e)[:300]
            _db.upsert_df(
                f"{M}.lens_filings_state",
                pd.DataFrame(
                    [
                        {
                            "instrument_id": iid,
                            "symbol": sym,
                            "status": "error",
                            "filings": None,
                            "error": msg,
                            "updated_at": dt.datetime.now(dt.UTC),
                        }
                    ]
                ),
                ["instrument_id"],
            )
            err += 1
            if any(t in msg for t in ("403", "401", "Connection", "Timeout")):
                s = _session()
        if n % 25 == 0 or n == total:
            print(
                f"[filings] {n}/{total} done={done} err={err} filings={ftot} last={sym}", flush=True
            )
        time.sleep(1.0)
    print(f"[filings] COMPLETE done={done} err={err} filings={ftot}", flush=True)
    return {"targets": total, "done": done, "err": err, "filings": ftot}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    run(only_pending=not a.redo, limit=a.limit)
