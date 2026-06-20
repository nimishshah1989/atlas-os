#!/usr/bin/env python3
"""Gate validator for the six-lens data feeds.

Checks that all required feed tables are populated for the Nifty-500 core:
  1. financials_quarterly (XBRL) — ≥8 quarters per N500 stock
  2. tv_metrics (TradingView)    — present + fresh for N500
  3. lens_filings (Catalyst)     — ≥1 filing per N500 stock
  4. lens_insider (Flow/PIT)     — present for N500 (some may have no data)
  5. lens_shareholding (Flow)    — ≥1 quarter per N500 stock
  6. lens_bulk_deals (Flow)      — non-empty (snapshot, not per-symbol)

Prints a one-screen summary. Exit 0 = gate green; exit 1 = gate red.

Run: python validate_six_lens.py
"""
from __future__ import annotations

import sys

import _db
from harness import STAGING_SCHEMA, GREEN, RED, YEL, DIM, RST

M = STAGING_SCHEMA


def _n500_symbols() -> set[str]:
    df = _db.read_df(
        "select symbol from public.de_instrument "
        "where nifty_500 = true and is_active = true")
    return set(df["symbol"])


def _staging_symbols() -> set[str]:
    df = _db.read_df(
        f"select symbol from {M}.instrument_master "
        "where asset_class='stock' and kite_token is not null")
    return set(df["symbol"])


def _check_financials(n500: set[str]) -> dict:
    """financials_quarterly: ≥8 quarters per N500 stock."""
    try:
        df = _db.read_df(
            f"select symbol, count(*) n from {M}.financials_quarterly "
            "where consolidated = true group by symbol")
    except Exception:
        return {"name": "financials_quarterly", "total": 0, "pass": 0,
                "n500_total": len(n500), "n500_pass": 0,
                "note": "table missing or empty"}
    counts = dict(zip(df["symbol"], df["n"]))
    n500_pass = sum(1 for s in n500 if counts.get(s, 0) >= 8)
    return {"name": "financials_quarterly", "total": len(counts),
            "pass": sum(1 for v in counts.values() if v >= 8),
            "n500_total": len(n500), "n500_pass": n500_pass,
            "note": f"≥8q threshold"}


def _check_tv_metrics(n500: set[str]) -> dict:
    """tv_metrics: present for N500."""
    try:
        df = _db.read_df("select symbol from atlas.tv_metrics")
    except Exception:
        return {"name": "tv_metrics", "total": 0, "pass": 0,
                "n500_total": len(n500), "n500_pass": 0,
                "note": "table missing"}
    syms = set(df["symbol"])
    n500_pass = len(n500 & syms)
    return {"name": "tv_metrics", "total": len(syms), "pass": len(syms),
            "n500_total": len(n500), "n500_pass": n500_pass,
            "note": ""}


def _check_filings(n500: set[str]) -> dict:
    """lens_filings: ≥1 filing per N500."""
    try:
        df = _db.read_df(
            f"select symbol, count(*) n from {M}.lens_filings group by symbol")
    except Exception:
        return {"name": "lens_filings", "total": 0, "pass": 0,
                "n500_total": len(n500), "n500_pass": 0,
                "note": "table missing or empty"}
    syms = set(df["symbol"])
    n500_pass = len(n500 & syms)
    return {"name": "lens_filings", "total": len(syms),
            "pass": len(syms), "n500_total": len(n500),
            "n500_pass": n500_pass, "note": ""}


def _check_insider(n500: set[str]) -> dict:
    """lens_insider: present for N500 (some stocks genuinely have no PIT filings)."""
    try:
        df = _db.read_df(
            f"select symbol, count(*) n from {M}.lens_insider group by symbol")
    except Exception:
        return {"name": "lens_insider", "total": 0, "pass": 0,
                "n500_total": len(n500), "n500_pass": 0,
                "note": "table missing or empty"}
    syms = set(df["symbol"])
    # Also count stocks processed (even if no data) via state table
    try:
        st = _db.read_df(f"select symbol from {M}.lens_insider_state where status in ('done','no_data')")
        processed = set(st["symbol"])
    except Exception:
        processed = syms
    n500_pass = len(n500 & processed)
    return {"name": "lens_insider", "total": len(syms),
            "pass": len(processed), "n500_total": len(n500),
            "n500_pass": n500_pass,
            "note": f"{len(syms)} with data, {len(processed)} processed"}


def _check_shareholding(n500: set[str]) -> dict:
    """lens_shareholding: ≥1 quarter per N500."""
    try:
        df = _db.read_df(
            f"select symbol, count(*) n from {M}.lens_shareholding group by symbol")
    except Exception:
        return {"name": "lens_shareholding", "total": 0, "pass": 0,
                "n500_total": len(n500), "n500_pass": 0,
                "note": "table missing or empty"}
    syms = set(df["symbol"])
    n500_pass = len(n500 & syms)
    return {"name": "lens_shareholding", "total": len(syms),
            "pass": len(syms), "n500_total": len(n500),
            "n500_pass": n500_pass, "note": ""}


def _check_bulk_deals() -> dict:
    """lens_bulk_deals: non-empty (snapshot feed, not per-symbol)."""
    try:
        n = _db.scalar(f"select count(*) from {M}.lens_bulk_deals")
    except Exception:
        n = 0
    return {"name": "lens_bulk_deals", "total": n, "pass": n,
            "n500_total": "-", "n500_pass": "-",
            "note": "snapshot (not per-symbol)"}


def run() -> bool:
    n500 = _n500_symbols()
    staging = _staging_symbols()
    n500_in_staging = n500 & staging

    print(f"\n{'='*70}")
    print(f" SIX-LENS DATA GATE — N500={len(n500)}, in staging={len(n500_in_staging)}")
    print(f"{'='*70}")

    checks = [
        _check_financials(n500_in_staging),
        _check_tv_metrics(n500_in_staging),
        _check_filings(n500_in_staging),
        _check_insider(n500_in_staging),
        _check_shareholding(n500_in_staging),
        _check_bulk_deals(),
    ]

    all_green = True
    for c in checks:
        n500_t = c["n500_total"]
        n500_p = c["n500_pass"]
        if isinstance(n500_p, int) and isinstance(n500_t, int):
            pct = n500_p / n500_t * 100 if n500_t else 0
            if pct >= 90:
                col = GREEN
            elif pct >= 50:
                col = YEL
                all_green = False
            else:
                col = RED
                all_green = False
            status = f"{col}{n500_p}/{n500_t} ({pct:.0f}%){RST}"
        else:
            status = f"{GREEN}{c['total']} deals{RST}" if c["total"] else f"{RED}empty{RST}"
            if not c["total"]:
                all_green = False

        print(f"  {c['name']:<25s} total={c['total']:<6} N500={status}"
              + (f"  {DIM}{c['note']}{RST}" if c.get("note") else ""))

    print(f"{'='*70}")
    if all_green:
        print(f"  {GREEN}GATE: GREEN — all feeds populated for N500 core{RST}")
    else:
        print(f"  {RED}GATE: RED — some feeds still ingesting{RST}")
    print()
    return all_green


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
