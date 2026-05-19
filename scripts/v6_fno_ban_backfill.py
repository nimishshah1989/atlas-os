"""Backfill NSE F&O ban list from 2017-01-01 to today (trading days only).

Uses atlas_universe_stocks (symbol → instrument_id) because this v6 DB does
not have atlas_instrument_master. Creates atlas_governance_daily if absent.
"""

from __future__ import annotations

import io
import os
import time
from datetime import date

import pandas as pd
import requests
import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

log = structlog.get_logger()

BASE_URL = "https://archives.nseindia.com/content/fo"

# Pretend to be a browser — NSE rejects bare requests user-agents
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def ensure_table(session) -> None:
    """Create atlas_governance_daily if migration 080 didn't land it."""
    session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_governance_daily (
            instrument_id        UUID NOT NULL,
            date                 DATE NOT NULL,
            pledge_ratio_pct     NUMERIC(6,2),
            in_fno_ban_list      BOOLEAN,
            PRIMARY KEY (instrument_id, date)
        );
    """)
    )
    session.execute(
        text("""
        CREATE INDEX IF NOT EXISTS ix_atlas_governance_daily_date
            ON atlas.atlas_governance_daily (date);
    """)
    )
    session.commit()
    log.info("table_ensured", table="atlas_governance_daily")


def load_symbol_map(session) -> dict[str, str]:
    """Return symbol → instrument_id (str) from atlas_universe_stocks."""
    rows = session.execute(
        text("SELECT symbol, instrument_id FROM atlas.atlas_universe_stocks")
    ).fetchall()
    mapping = {r.symbol: str(r.instrument_id) for r in rows}
    log.info("symbol_map_loaded", n=len(mapping))
    return mapping


def trading_days(start: date, end: date, session) -> list[date]:
    """Pull trading days from atlas_market_regime_daily."""
    rows = session.execute(
        text(
            "SELECT date FROM atlas.atlas_market_regime_daily "
            "WHERE date BETWEEN :s AND :e ORDER BY date"
        ),
        {"s": start, "e": end},
    ).fetchall()
    return [r.date for r in rows]


def fetch_ban_for_date(ref_date: date) -> set[str]:
    """Fetch NSE F&O ban list for ref_date. Returns set of symbols (may be empty)."""
    if ref_date == date.today():
        url = f"{BASE_URL}/fo_secban.csv"
    else:
        url = f"{BASE_URL}/secban_{ref_date.strftime('%d%m%Y')}.csv"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        log.warning("fno_ban_request_error", url=url, err=str(exc)[:80])
        return set()

    if resp.status_code == 404:
        # Old archive files simply may not exist for some dates — treat as no ban
        return set()

    if resp.status_code != 200:
        log.warning("fno_ban_fetch_failed", url=url, status=resp.status_code)
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")

    text_body = resp.text.strip()
    if not text_body:
        return set()

    try:
        df = pd.read_csv(io.StringIO(text_body))
    except Exception:
        return set()

    if df.empty:
        return set()

    col = next((c for c in df.columns if "symbol" in c.lower()), None)
    if col is None:
        log.warning("fno_ban_no_symbol_col", url=url, columns=list(df.columns))
        return set()

    return set(df[col].astype(str).str.strip().tolist())


def upsert_ban_day(session, ref_date: date, ban_symbols: set[str], sym_map: dict[str, str]) -> int:
    """
    Upsert ban flags for ref_date.

    Returns count of matched (universe) symbols marked banned.
    """
    matched_iids: list[str] = [sym_map[s] for s in ban_symbols if s in sym_map]

    # Mark banned symbols
    for iid in matched_iids:
        session.execute(
            text("""
            INSERT INTO atlas.atlas_governance_daily
                (instrument_id, date, in_fno_ban_list)
            VALUES (:i, :d, true)
            ON CONFLICT (instrument_id, date) DO UPDATE
               SET in_fno_ban_list = true
        """),
            {"i": iid, "d": ref_date},
        )

    # Clear stale true flags for symbols no longer on ban list today
    if matched_iids:
        session.execute(
            text("""
            UPDATE atlas.atlas_governance_daily
               SET in_fno_ban_list = false
             WHERE date = :d
               AND in_fno_ban_list = true
               AND instrument_id != ALL(:iids::uuid[])
        """),
            {"d": ref_date, "iids": matched_iids},
        )
    else:
        # No universe symbols banned today — clear all true flags for this date
        session.execute(
            text("""
            UPDATE atlas.atlas_governance_daily
               SET in_fno_ban_list = false
             WHERE date = :d AND in_fno_ban_list = true
        """),
            {"d": ref_date},
        )

    session.commit()
    return len(matched_iids)


def main() -> None:
    eng = create_engine(os.environ["ATLAS_DB_URL"])
    session_factory = sessionmaker(bind=eng)
    session = session_factory()

    ensure_table(session)
    sym_map = load_symbol_map(session)

    start = date(2017, 1, 1)
    end = date.today()
    days = trading_days(start, end, session)
    log.info("backfill_starting", n_days=len(days), start=start.isoformat(), end=end.isoformat())

    success = 0
    misses = 0
    rate_limited = 0

    for i, d in enumerate(days):
        try:
            syms = fetch_ban_for_date(d)
            matched = upsert_ban_day(session, d, syms, sym_map)
            success += 1
            if i % 50 == 0:
                log.info(
                    "progress",
                    date=d.isoformat(),
                    i=i,
                    n=len(days),
                    ban_raw=len(syms),
                    ban_universe_matched=matched,
                    success=success,
                    misses=misses,
                )
        except RuntimeError as exc:
            err_str = str(exc)
            if "429" in err_str or "403" in err_str:
                rate_limited += 1
                log.warning(
                    "rate_limited",
                    date=d.isoformat(),
                    err=err_str[:80],
                    rate_limited_total=rate_limited,
                )
                if rate_limited >= 10:
                    log.error("too_many_rate_limits", stopping=True)
                    break
                time.sleep(5)  # Back off on rate limit
            else:
                misses += 1
                log.warning("day_missed", date=d.isoformat(), err=err_str[:80])
        except Exception as exc:
            misses += 1
            log.warning("day_missed", date=d.isoformat(), err=str(exc)[:80])

        time.sleep(0.6)  # Polite to NSE archive

    log.info(
        "backfill_complete",
        success=success,
        misses=misses,
        rate_limited=rate_limited,
        total_days=len(days),
    )


if __name__ == "__main__":
    main()
