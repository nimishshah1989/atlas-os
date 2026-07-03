#!/usr/bin/env python3
"""Macro-overlay ingest → atlas_foundation.atlas_macro_daily.

The market-pulse macro strip reads this table; its producer (atlas/ingest/macro/*,
a 5-source FRED + Yahoo-VIX + NSE-FII/DII + MOSPI-CPI runner) was deleted in the
consolidation, so the table froze at 06-25.

This is the LEAN replacement scoped to what the board actually renders
(market_pulse.ts): usdinr, dxy, india_10y_yield, us_10y_yield, brent_inr,
cpi_yoy, fii_cash_equity_flow_cr, dii_flow.

Two tiers, all REAL values (RULE #0 — nothing fabricated):
  * FRESH FRED daily — usdinr (DEXINUS), dxy (DTWEXBGS), us_10y_yield (DGS10),
    brent_inr (DCOILBRENTEU × usdinr). Forward-filled onto the NSE trading
    calendar (FRED's US-holiday gaps don't align with NSE). NOTE: usdinr + dxy
    were NEVER populated by the old runner (perpetually NULL) — FRED fills them.
  * CARRY-FORWARD lagging series — india_10y_yield, cpi_yoy, fii_cash_equity_flow_cr,
    dii_flow. FRED's India CPI lags ~15 months and India-10Y is monthly/behind the
    DB, and NSE FII/DII (monthly net flows) has no reliable free feed. The old
    runner ALSO forward-filled these monthly values across daily rows, so we carry
    each column's last REAL value into the new trading dates — the established
    behaviour, not a new number. They self-correct when a fresh point arrives.

Run daily (atlas_daily.sh). Idempotent.
"""

from __future__ import annotations

import os

import _db
import pandas as pd
import requests

M = "atlas_foundation"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_DAILY = {"usdinr": "DEXINUS", "dxy": "DTWEXBGS", "us_10y_yield": "DGS10"}
BRENT_SERIES = "DCOILBRENTEU"
CARRY_COLS = ["india_10y_yield", "cpi_yoy", "fii_cash_equity_flow_cr", "dii_flow"]
HISTORY_START = "2026-04-01"  # ~60 trading days — enough for the strip's 1d/1m deltas


def _fred(series: str, start: str) -> dict[str, float]:
    key = os.environ["FRED_API_KEY"]  # KeyError if unset — fail loud, don't fabricate
    r = requests.get(
        FRED_BASE,
        params={
            "series_id": series,
            "api_key": key,
            "file_type": "json",
            "observation_start": start,
        },
        timeout=30,
    )
    r.raise_for_status()
    return {
        o["date"]: float(o["value"])
        for o in r.json().get("observations", [])
        if o.get("value") not in (".", "", None)
    }


def _ffill_onto(cal: list, obs: dict[str, float]) -> dict:
    """Map each calendar date to the latest FRED observation on/before it."""
    keys = sorted(obs)
    out, j, last = {}, 0, None
    for d in cal:
        ds = str(d)
        while j < len(keys) and keys[j] <= ds:
            last = obs[keys[j]]
            j += 1
        out[d] = last
    return out


def _ensure_unique_date() -> None:
    """atlas_macro_daily shipped with only a non-unique date index; upsert_df's
    ON CONFLICT (date) needs a unique key. Dedup any same-date rows, then add it."""
    if _db.scalar(
        "select 1 from pg_indexes where schemaname=:s and tablename='atlas_macro_daily' "
        "and indexname='ux_atlas_macro_daily_date'",
        {"s": M},
    ):
        return
    _db.exec_sql(
        f"delete from {M}.atlas_macro_daily a using {M}.atlas_macro_daily b "
        "where a.ctid < b.ctid and a.date = b.date"
    )
    _db.exec_sql(f"create unique index ux_atlas_macro_daily_date on {M}.atlas_macro_daily (date)")


def build() -> None:
    _ensure_unique_date()
    eod = _db.eod_cutoff()
    cal = list(
        _db.read_df(
            f"select distinct date from {M}.technical_daily "
            "where asset_class='stock' and date >= :s and date <= :e order by date",
            {"s": HISTORY_START, "e": eod},
        )["date"]
    )
    if not cal:
        raise RuntimeError("no NSE trading dates in window — technical_daily empty?")
    old_max = _db.scalar(f"select max(date) from {M}.atlas_macro_daily")

    # ── tier 1: fresh FRED daily, ffilled onto the NSE calendar ──
    daily = {col: _ffill_onto(cal, _fred(sid, "2026-03-01")) for col, sid in FRED_DAILY.items()}
    brent = _ffill_onto(cal, _fred(BRENT_SERIES, "2026-03-01"))
    rows = []
    for d in cal:
        u, b = daily["usdinr"][d], brent[d]
        rows.append(
            {
                "date": d,
                "usdinr": u,
                "dxy": daily["dxy"][d],
                "us_10y_yield": daily["us_10y_yield"][d],
                "brent_inr": (round(b * u, 4) if (b is not None and u is not None) else None),
            }
        )
    dfA = pd.DataFrame(rows)
    _db.upsert_df(f"{M}.atlas_macro_daily", dfA, ["date"])

    # ── tier 2: carry each lagging column's last REAL value into the new trading dates ──
    new_dates = [d for d in cal if old_max is None or d > old_max]
    carried = {}
    if new_dates:
        carry_rows = []
        for d in new_dates:
            row = {"date": d}
            for col in CARRY_COLS:
                last = _db.scalar(
                    f"select {col} from {M}.atlas_macro_daily "
                    f"where {col} is not null and date < :d order by date desc limit 1",
                    {"d": d},
                )
                row[col] = last
                carried[col] = last
            carry_rows.append(row)
        _db.upsert_df(f"{M}.atlas_macro_daily", pd.DataFrame(carry_rows), ["date"])

    latest = dfA.iloc[-1]
    print(f"[macro] eod={eod} calendar={len(cal)}d new_dates={len(new_dates)} (old_max={old_max})")
    print(
        f"[macro] fresh @ {latest['date']}: usdinr={latest['usdinr']} dxy={latest['dxy']} "
        f"us10y={latest['us_10y_yield']} brent_inr={latest['brent_inr']}"
    )
    if new_dates:
        print(f"[macro] carried-forward into new dates: {carried}")


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
