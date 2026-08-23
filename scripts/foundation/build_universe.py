#!/usr/bin/env python3
"""Build the authoritative instrument master → atlas_foundation.instrument_master.

Universe = what we can source cleanly from Kite:
  • stocks  — NSE's official EQUITY_L.csv (symbol, name, series, ISIN, listing),
              mapped to a Kite instrument_token.
  • etfs    — Kite NSE cash instruments that look like ETFs (name/symbol markers)
              and are not in EQUITY_L.
  • indices — Kite's INDICES segment (NIFTY 50/500/BANK + sector/thematic).

instrument_id continuity: reuse the EXISTING atlas_foundation.instrument_master id
where the stock symbol matches (so existing Atlas instrument_ids keep working);
otherwise a deterministic uuid5 of the symbol. Idempotent: safe to re-run.

`--dry-run` computes the would-be active set and prints the diff vs the current
instrument_master WITHOUT writing — use it to prove the scored universe is stable
before the weekly cron mutates it.
"""

from __future__ import annotations

import argparse
import io
import re
import uuid
from decimal import Decimal

import _db
import build_universe_snapshot as _snap
import pandas as pd
import requests
import universe_core as U

_NS = uuid.UUID("6f9b1f6e-0000-4000-8000-a71a5000c0de")  # fixed namespace for uuid5
EQUITY_L = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
# NSE's ETF securities master — the authoritative ISIN for every listed ETF.
# ETF rows used to be built from the Kite dump alone, which carries no ISIN, so
# two-thirds of ETFs sat at isin NULL and any ISIN join silently missed them
# (GOLDBEES, SILVERBEES, BANKBEES, LIQUIDCASE, JUNIORBEES...). Worse, this file
# recreates ETF rows on every run, so the weekly build actively re-emptied the
# column. Sourcing the ISIN here fixes it at the source instead of downstream.
ETF_L = "https://archives.nseindia.com/content/equities/eq_etfseclist.csv"
_H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}

# An instrument is an ETF if its symbol or name carries one of these markers.
_ETF_MARKERS = re.compile(
    r"(ETF|BEES|IETF|NASDAQ|HANGSENG|\bFANG\b|SENSEX|NIFTY|GOLD|SILVER|LIQUID|"
    r"BOND|GSEC|SDL|MOMENTUM|ALPHA|VALUE|QUALITY|LOWVOL|CONSUMPTION|PSUBANK|"
    r"HEALTHCARE|MIDCAP|SMALLCAP|INFRA|DIVOPP|CPSE|BHARAT22)",
    re.I,
)


def uuid_for(kind: str, symbol: str) -> str:
    return str(uuid.uuid5(_NS, f"nse:{kind}:{symbol}"))


def fetch_equity_list() -> pd.DataFrame:
    raw = requests.get(EQUITY_L, headers=_H, timeout=30).content
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame(
        {
            "symbol": df["SYMBOL"].astype(str).str.strip(),
            "name": df["NAME OF COMPANY"].astype(str).str.strip(),
            "series": df["SERIES"].astype(str).str.strip(),
            "isin": df["ISIN NUMBER"].astype(str).str.strip(),
            "listing_date": pd.to_datetime(
                df["DATE OF LISTING"], format="%d-%b-%Y", errors="coerce"
            ).dt.date,
        }
    )
    return out


def fetch_etf_list() -> dict[str, tuple[str, object]]:
    """symbol -> (isin, listing_date) from NSE's ETF securities master.

    latin-1: the file carries en-dashes in scheme names and is not UTF-8.
    Returns {} on any failure — a transient NSE outage must not wipe the ISINs
    already in the table, and the caller leaves existing values untouched.
    """
    try:
        raw = requests.get(ETF_L, headers=_H, timeout=30).content
        df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")
    except Exception as exc:
        print(f"WARN fetch_etf_list failed ({exc}) — ETF ISINs left as-is")
        return {}
    df.columns = [c.strip() for c in df.columns]
    listed = pd.to_datetime(df["DateofListing"], format="%d-%b-%y", errors="coerce").dt.date
    return {
        str(s).strip(): (str(i).strip(), d)
        for s, i, d in zip(df["Symbol"], df["ISINNumber"], listed, strict=False)
        if str(i).strip()
    }


def liquid_universe(floor_inr: Decimal | None = None) -> set[str]:
    """instrument_ids in Atlas coverage: ADV over the floor, or held in a book.

    Composes the shipped rule — it does not restate it. The ADV SQL lives in
    build_universe_snapshot.adv_frame() and the membership test in
    universe_core.members(); a second copy of either is how ten copies of the cap rule
    happened.

    floor_inr defaults to atlas_thresholds.liquidity_min_traded_value_inr. It is a
    parameter only so tests can prove the threshold drives the rule (a stricter floor
    must yield a strict subset) — production never passes it.
    """
    as_of = _snap.snapshot_date()
    if as_of is None:
        raise RuntimeError("no atlas_foundation.ohlcv_stock rows at or before the cutoff")
    adv = _snap.adv_frame(
        as_of,
        int(_snap.threshold(U.THRESHOLD_KEY_MIN_OBS)),
        int(_snap.threshold(U.THRESHOLD_KEY_RECENCY)),
    )
    floor = _snap.threshold(U.THRESHOLD_KEY) if floor_inr is None else floor_inr
    return U.members(adv, floor, _snap.held_ids(as_of))


def build(dry_run: bool = False) -> dict:
    # Imported here, not at module scope: ingest_kite pulls in the talib native
    # extension, which is installed on the box but is not a declared dependency — a
    # module-scope import makes liquid_universe() unimportable (and so untestable)
    # anywhere talib is absent. Single call site, two lines below.
    import ingest_kite as ik

    eq = fetch_equity_list()
    etf_ident = fetch_etf_list()
    eq_syms = set(eq["symbol"])

    kite = ik.kite_client()
    nse = kite.instruments("NSE")
    cash_tok = {
        i["tradingsymbol"]: int(i["instrument_token"]) for i in nse if i["segment"] == "NSE"
    }
    cash_name = {i["tradingsymbol"]: (i.get("name") or "") for i in nse if i["segment"] == "NSE"}
    idx = [i for i in nse if i["segment"] == "INDICES"]

    # instrument_id continuity is now self-sourced from instrument_master (the canonical
    # ids descend from the former public.de_instrument, which was dropped in the
    # single-schema consolidation). Existing ids are preserved; new symbols get a uuid5.
    de = _db.read_df(
        "select instrument_id as id, symbol from atlas_foundation.instrument_master "
        "where asset_class = 'stock'"
    )
    de_id = {str(r.symbol).strip(): str(r.id) for r in de.itertuples()}

    # Coverage universe = ONE liquidity floor: trailing 60-day MEDIAN daily traded value
    # >= atlas_thresholds.liquidity_min_traded_value_inr (methodology §3.3), plus any
    # stock held in a portfolio book. is_active means "in Atlas coverage", NOT
    # "tradeable on NSE" — it scopes the data-integrity gate's "every active stock has a
    # sector" / "≤21 canonical sectors" checks to the board universe.
    #
    # Was NIFTY 500 ∪ NIFTY MICROCAP250 = 750, which IS NSE's Nifty Total Market — the
    # largest index that exists, so the index rule could never exceed 750 (FM, 2026-08-23).
    # Data sufficiency is NOT gated here: compute_composite() already does a
    # coverage-adjusted weighted average, so a liquid name with no financials gets a
    # NULL fundamental lens rather than a fabricated score (rule #0).
    coverage_ids = liquid_universe()

    rows = []
    # stocks
    for r in eq.itertuples():
        iid = de_id.get(r.symbol) or uuid_for("stock", r.symbol)
        rows.append(
            (
                iid,
                "stock",
                r.symbol,
                r.name,
                r.isin,
                r.series,
                r.listing_date,
                cash_tok.get(r.symbol),
                "NSE",
                iid in coverage_ids,
                "NSE_EQUITY_L",
            )
        )
    # etfs — cash instruments not in EQUITY_L whose symbol/name looks like an ETF.
    # Exclude indicative-NAV feed instruments (…INAV / "NAV"): not tradeable.
    for sym, tok in cash_tok.items():
        if sym in eq_syms or not re.fullmatch(r"[A-Z0-9]+", sym):
            continue
        nm = cash_name.get(sym, "")
        if "INAV" in sym.upper() or re.search(r"\bI?NAV\b", nm, re.I):
            continue
        if _ETF_MARKERS.search(sym) or _ETF_MARKERS.search(nm):
            isin, listed = etf_ident.get(sym, (None, None))
            rows.append(
                (
                    uuid_for("etf", sym),
                    "etf",
                    sym,
                    cash_name.get(sym),
                    isin,
                    None,
                    listed,
                    tok,
                    "NSE",
                    True,
                    "NSE_ETF_L" if isin else "KITE_NSE_ETF",
                )
            )
    # indices
    for i in idx:
        sym = i["tradingsymbol"]
        rows.append(
            (
                uuid_for("index", sym),
                "index",
                sym,
                i.get("name"),
                None,
                None,
                None,
                int(i["instrument_token"]),
                "NSE",
                True,
                "KITE_INDICES",
            )
        )

    cols = [
        "instrument_id",
        "asset_class",
        "symbol",
        "name",
        "isin",
        "series",
        "listing_date",
        "kite_token",
        "exchange",
        "is_active",
        "source",
    ]
    df = pd.DataFrame(rows, columns=cols).drop_duplicates("instrument_id")

    # Before/after guardrail: prove the scored universe (active stocks) is stable before
    # the write. Membership can legitimately drift as names cross the liquidity floor;
    # the diff surfaces exactly which symbols flip so a change is never silent.
    cur_active = set(
        _db.read_df(
            "select instrument_id::text id from atlas_foundation.instrument_master "
            "where asset_class = 'stock' and is_active"
        )["id"]
    )
    new_active = set(df.loc[(df["asset_class"] == "stock") & (df["is_active"]), "instrument_id"])
    added, removed = new_active - cur_active, cur_active - new_active
    print(
        f"  active stocks: {len(cur_active)} -> {len(new_active)} (+{len(added)} / -{len(removed)})"
    )
    if added or removed:
        sym = {str(r.instrument_id): r.symbol for r in df.itertuples()}
        if added:
            print("    ADDED:  ", ", ".join(sorted(sym.get(i, i) for i in added)))
        if removed:
            # :ids, not %(ids)s — _db.read_df wraps the SQL in SQLAlchemy text(), which
            # rejects psycopg2 placeholders. This branch only runs when a symbol LEAVES
            # the universe, so the error stayed latent: every index reconstitution
            # aborted the weekly build before it wrote anything, which is why
            # instrument_master drifted (docs/table-census.md#L187).
            rem = _db.read_df(
                "select instrument_id::text id, symbol from atlas_foundation.instrument_master "
                "where instrument_id::text = any(cast(:ids as text[]))",
                {"ids": list(removed)},
            )
            print("    REMOVED:", ", ".join(sorted(rem["symbol"])))

    if dry_run:
        print("  DRY RUN — no write.")
        by = df.groupby("asset_class").size().to_dict()
        return {"written": 0, "dry_run": True, "would_write": len(df), "by_class": by}

    df["updated_at"] = pd.Timestamp.now(tz="Asia/Kolkata")  # stamp the refresh (G6 freshness)
    n = _db.upsert_df("atlas_foundation.instrument_master", df, ["instrument_id"])

    counts = (
        df.groupby("asset_class")
        .agg(total=("symbol", "size"), on_kite=("kite_token", lambda s: int(s.notna().sum())))
        .to_dict("index")
    )
    return {"written": n, "by_class": counts}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="compute + diff the universe, no write")
    args = ap.parse_args()
    print(build(dry_run=args.dry_run))
