"""Ingest NSE forthcoming corporate events → atlas_foundation.lens_events.

Forward-looking companion to ingest_filings.py (which is PAST announcements).
NSE's event-calendar publishes upcoming board meetings, dividends, buybacks,
splits etc. with their scheduled dates — the source for "who reports in the
next 7/15 days". One call returns the whole market's calendar, so unlike the
per-symbol filings feed this is a single fetch.

    python scripts/foundation/ingest_events.py            # next 45 days
    python scripts/foundation/ingest_events.py --days 90

RULE #0: every row is a real NSE-published event; nothing synthesised.
"""

from __future__ import annotations

import argparse
import datetime as dt

import _db
import pandas as pd
import requests
from harness import STAGING_SCHEMA

M = STAGING_SCHEMA

_H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/118.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar",
}
_API = "https://www.nseindia.com/api/event-calendar"

# purpose keyword → (normalised event_type, priority). Longest match wins.
_PURPOSE: dict[str, tuple[str, str]] = {
    "financial result": ("earnings", "HIGH"),
    "results": ("earnings", "HIGH"),
    "buy back": ("buyback", "HIGH"),
    "buyback": ("buyback", "HIGH"),
    "bonus": ("bonus", "HIGH"),
    "stock split": ("split", "HIGH"),
    "split": ("split", "HIGH"),
    "sub-division": ("split", "HIGH"),
    "rights issue": ("rights", "HIGH"),
    "rights": ("rights", "HIGH"),
    "amalgamation": ("restructuring", "HIGH"),
    "merger": ("restructuring", "HIGH"),
    "scheme of arrangement": ("restructuring", "HIGH"),
    "voluntary delisting": ("delisting", "HIGH"),
    "fund raising": ("capital", "MEDIUM"),
    "raising of funds": ("capital", "MEDIUM"),
    "preferential": ("capital", "MEDIUM"),
    "dividend": ("dividend", "MEDIUM"),
}


def classify_purpose(purpose: str) -> tuple[str, str]:
    p = (purpose or "").lower()
    for kw in sorted(_PURPOSE, key=len, reverse=True):
        if kw in p:
            return _PURPOSE[kw]
    return "other", "LOW"


def _parse_date(s: str) -> dt.date | None:
    for fmt in ("%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime((s or "").strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def ddl() -> None:
    _db.exec_script(f"""
    create table if not exists {M}.lens_events (
        instrument_id uuid not null,
        symbol text not null,
        event_date date not null,
        purpose text not null,
        event_type text not null,
        priority text not null,
        description text,
        company text,
        source text not null default 'NSE',
        ingested_at timestamptz not null default now(),
        primary key (instrument_id, event_date, purpose)
    );
    create index if not exists lens_events_date_idx on {M}.lens_events (event_date);
    """)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_H)
    s.get("https://www.nseindia.com/", timeout=20)
    s.get("https://www.nseindia.com/option-chain", timeout=20)
    return s


def run(days: int = 45) -> dict:
    ddl()
    # symbol -> instrument_id for the tracked universe. Events for symbols we don't
    # track are dropped (can't link them to a scored name or a deep-dive page).
    im = _db.read_df(
        f"select instrument_id::text iid, symbol from {M}.instrument_master where asset_class='stock'"
    )
    sym2iid = dict(zip(im["symbol"], im["iid"], strict=True))

    today = dt.date.today()
    s = _session()
    r = s.get(
        _API,
        params={
            "index": "equities",
            "from_date": today.strftime("%d-%m-%Y"),
            "to_date": (today + dt.timedelta(days=days)).strftime("%d-%m-%Y"),
        },
        timeout=45,
    )
    r.raise_for_status()
    payload = r.json()
    raw = payload if isinstance(payload, list) else payload.get("data", [])
    print(f"[events] NSE returned {len(raw)} events for the next {days}d", flush=True)

    rows, unmapped = [], 0
    for rec in raw:
        sym = (rec.get("symbol") or "").strip()
        iid = sym2iid.get(sym)
        if not iid:
            unmapped += 1
            continue
        ev_date = _parse_date(rec.get("date"))
        if not ev_date or ev_date < today:
            continue
        purpose = (rec.get("purpose") or "").strip() or "Event"
        etype, prio = classify_purpose(purpose)
        rows.append(
            {
                "instrument_id": iid,
                "symbol": sym,
                "event_date": ev_date,
                "purpose": purpose,
                "event_type": etype,
                "priority": prio,
                "description": (rec.get("bm_desc") or None),
                "company": (rec.get("company") or None),
                "ingested_at": dt.datetime.now(dt.UTC),
            }
        )

    if rows:
        _db.upsert_df(
            f"{M}.lens_events",
            pd.DataFrame(rows),
            ["instrument_id", "event_date", "purpose"],
        )
    # Drop events that have aged out so the table stays a forward window.
    _db.exec_sql(
        f"delete from {M}.lens_events where event_date < :d", {"d": today - dt.timedelta(days=3)}
    )
    print(f"[events] upserted={len(rows)} tracked, dropped_unmapped={unmapped}", flush=True)
    return {"fetched": len(raw), "upserted": len(rows), "unmapped": unmapped}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    a = ap.parse_args()
    run(days=a.days)
