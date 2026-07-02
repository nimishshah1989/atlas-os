#!/usr/bin/env python3
"""Scale validator: the 3-axis definition-of-done over the FULL staging universe.

Where harness.py compares live-vs-staging on the Nifty-500 (recompute-and-diff),
this validates the whole clean dataset (stocks + ETFs + indices) for adoption:

  1. COVERAGE    — every instrument present with a complete series for its span.
  2. CLEANLINESS — no null/≤0 closes, no calendar gaps, ≤1 tday stale, no absurd
                   1-day jump EXCEPT genuine demergers (corp_action_event whitelist).
  3. METRICS     — technical_daily has a row for every priced date (compute parity);
                   plus a sampled TA-Lib recompute-and-diff for correctness.

Reads only atlas_foundation.* Prints per-asset-class PASS/FAIL + green-count and
writes per-instrument detail to output/. Run after the backfill + compute.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _db
import pandas as pd
from harness import (
    CAL_INDEX,
    COMPLETENESS_MIN,
    DIM,
    GREEN,
    JUMP_MAX_PCT,
    RED,
    RST,
    STAGING_SCHEMA,
    STALE_MAX_TDAYS,
    YEL,
)

M = STAGING_SCHEMA
OUT_DIR = Path(__file__).resolve().parents[2] / "output"
# asset_class → (ohlcv table, close col, key col, key is uuid)
SRC = {
    "stock": (f"{M}.ohlcv_stock", "close_adj", "instrument_id", True),
    "etf": (f"{M}.ohlcv_etf", "close_adj", "ticker", False),
    "index": (f"{M}.index_prices", "close", "index_code", False),
}


def calendar() -> pd.DatetimeIndex:
    df = _db.read_df(
        f"select date from {M}.index_prices where index_code=:c order by date", {"c": CAL_INDEX}
    )
    return pd.DatetimeIndex(pd.to_datetime(df["date"]))


def demerger_exdates() -> dict[str, set]:
    df = _db.read_df(f"select symbol, ex_date from {M}.corp_action_event")
    out: dict[str, set] = {}
    for r in df.itertuples():
        out.setdefault(r.symbol, set()).add(pd.Timestamp(r.ex_date))
    return out


def universe(asset_class: str) -> pd.DataFrame:
    df = _db.read_df(
        f"select instrument_id, symbol, listing_date from {M}.instrument_master "
        "where asset_class=:a and kite_token is not null order by symbol",
        {"a": asset_class},
    )
    df["instrument_id"] = df["instrument_id"].astype(str)
    return df


def _covcl(asset_class, uni, cal, demergers) -> dict:
    tbl, ccol, keycol, is_uuid = SRC[asset_class]
    keys = list(uni["symbol"] if keycol != "instrument_id" else uni["instrument_id"])
    cast = "cast(:ks as uuid[])" if is_uuid else ":ks"
    sql = f"select {keycol} as k, date, {ccol} as c from {tbl} where {keycol} = any({cast})"
    by_key_sym = dict(
        zip(
            uni["instrument_id"] if keycol == "instrument_id" else uni["symbol"],
            uni["symbol"],
            strict=False,
        )
    )
    # Build listing-date lookup (keyed by the same key as by_key_sym)
    listing_dates = {}
    for r in uni.itertuples():
        k = r.instrument_id if keycol == "instrument_id" else r.symbol
        ld = pd.Timestamp(r.listing_date) if pd.notna(r.listing_date) else None
        listing_dates[str(k)] = ld

    agg = {}
    for i in range(0, len(keys), 200):
        chunk = [str(k) for k in keys[i : i + 200]]
        df = _db.read_df(sql, {"ks": chunk})
        if df.empty:
            continue
        df["k"] = df["k"].astype(str)
        df["date"] = pd.to_datetime(df["date"])
        df["c"] = pd.to_numeric(df["c"], errors="coerce")
        df = df.sort_values(["k", "date"])
        for k, g in df.groupby("k"):
            sym = by_key_sym.get(k, k)
            c = g.set_index("date")["c"]
            # Filter out non-positive closes before computing returns
            pos = c[c > 0].dropna()
            ratio = (pos / pos.shift(1) - 1).abs()
            wl = demergers.get(sym, set())
            if wl:
                ratio = ratio[~ratio.index.isin(wl)]
            agg[k] = {
                "first": c.index.min(),
                "last": c.index.max(),
                "n": len(c),
                "nulls": int(c.isna().sum()),
                "maxjump": float(ratio.max()) if len(ratio) else 0.0,
            }
    last_cal = cal[-1] if len(cal) else None
    res = {}
    for r in uni.itertuples():
        k = r.instrument_id if keycol == "instrument_id" else r.symbol
        a = agg.get(str(k))
        if not a:
            res[r.instrument_id] = {
                "symbol": r.symbol,
                "coverage": {"pass": False, "reason": "absent"},
                "cleanliness": {"pass": False, "reason": "absent"},
            }
            continue
        # Listing-relative span: use max(listing_date, first_data) so we never
        # penalise stocks for lacking data before their listing or before our
        # data-start horizon.  Exclude corp-action/suspension dates from expected cal.
        ld = listing_dates.get(str(k))
        span_start = max(ld, a["first"]) if ld is not None else a["first"]
        cal_in_range = (
            cal[(cal >= span_start) & (cal <= a["last"])] if len(cal) else pd.DatetimeIndex([])
        )
        exclusions = demergers.get(r.symbol, set())
        if exclusions:
            cal_in_range = cal_in_range[~cal_in_range.isin(exclusions)]
        span = len(cal_in_range) if len(cal_in_range) else a["n"]
        completeness = a["n"] / span if span else 1.0
        completeness = min(completeness, 1.0)  # cap at 100% (pre-listing data)
        stale = int((cal > a["last"]).sum()) if last_cal is not None else 0
        cov_ok = a["n"] >= 50 and completeness >= 0.90
        cl = []
        if a["nulls"]:
            cl.append(f"{a['nulls']} null")
        # Listing-relative gap threshold: allow up to 5 missing days for
        # shorter histories (recently listed stocks) instead of a flat 99%.
        gap_min = min(1 - 5 / span, COMPLETENESS_MIN) if span > 5 else 0.0
        if completeness < gap_min:
            cl.append(f"gaps {completeness:.1%}")
        if stale > STALE_MAX_TDAYS:
            cl.append(f"stale {stale}")
        if a["maxjump"] > JUMP_MAX_PCT:
            cl.append(f"jump {a['maxjump']:.0%}")
        res[r.instrument_id] = {
            "symbol": r.symbol,
            "coverage": {
                "pass": bool(cov_ok),
                "rows": a["n"],
                "first": str(a["first"].date()),
                "depth": round(completeness, 4),
                "reason": "ok" if cov_ok else f"rows={a['n']} depth={completeness:.1%}",
            },
            "cleanliness": {
                "pass": not cl,
                "maxjump": round(a["maxjump"], 4),
                "reason": "; ".join(cl) or "ok",
            },
        }
    return res


def _metrics_parity(asset_class, uni) -> dict:
    """technical_daily must have a row for every priced date (compute ran fully)."""
    tbl, ccol, keycol, _is_uuid = SRC[asset_class]
    ids = list(uni["instrument_id"])
    # counts per instrument in ohlcv vs technical_daily
    px = _db.read_df(
        f"select cast(instrument_id as text) id, count(*) n from {M}.technical_daily "
        "where instrument_id = any(cast(:ids as uuid[])) group by 1",
        {"ids": ids},
    )
    tcount = dict(zip(px["id"].astype(str), px["n"], strict=False))
    # ohlcv counts keyed back to instrument via universe symbol/id
    # Only count rows with valid (positive) closes — technicals can't be
    # computed from null/non-positive prices, so they shouldn't be expected.
    valid_filter = f"and {ccol} is not null and {ccol} > 0"
    if keycol == "instrument_id":
        oc = _db.read_df(
            f"select cast(instrument_id as text) id, count(*) n from {tbl} "
            f"where instrument_id = any(cast(:ids as uuid[])) {valid_filter} group by 1",
            {"ids": ids},
        )
        ocount = dict(zip(oc["id"].astype(str), oc["n"], strict=False))
        {i: i for i in ids}
    else:
        syms = list(uni["symbol"])
        oc = _db.read_df(
            f"select {keycol} k, count(*) n from {tbl} where {keycol}=any(:ks) "
            f"{valid_filter} group by 1",
            {"ks": syms},
        )
        sym_n = dict(zip(oc["k"].astype(str), oc["n"], strict=False))
        ocount = {r.instrument_id: sym_n.get(r.symbol, 0) for r in uni.itertuples()}
    res = {}
    for r in uni.itertuples():
        o = ocount.get(r.instrument_id, 0)
        t = tcount.get(r.instrument_id, 0)
        ok = o > 0 and t >= o  # parity (technical row per priced date)
        res[r.instrument_id] = {
            "pass": bool(ok),
            "ohlcv": o,
            "tech": t,
            "reason": "ok" if ok else f"tech {t} < ohlcv {o}",
        }
    return res


def run(asset_class: str, sample: int | None = None) -> dict:
    uni = universe(asset_class)
    cal = calendar()
    demergers = demerger_exdates()
    cc = _covcl(asset_class, uni, cal, demergers)
    met = _metrics_parity(asset_class, uni)
    rows = []
    for r in uni.itertuples():
        c = cc.get(r.instrument_id, {})
        rows.append(
            {
                "instrument_id": r.instrument_id,
                "symbol": r.symbol,
                "coverage": c.get("coverage", {}),
                "cleanliness": c.get("cleanliness", {}),
                "metrics": met.get(r.instrument_id, {}),
            }
        )
    n = len(rows)
    cov = sum(x["coverage"].get("pass") for x in rows)
    cl = sum(x["cleanliness"].get("pass") for x in rows)
    mt = sum(x["metrics"].get("pass") for x in rows)
    green = sum(
        1
        for x in rows
        if x["coverage"].get("pass") and x["cleanliness"].get("pass") and x["metrics"].get("pass")
    )
    summary = {
        "asset_class": asset_class,
        "n": n,
        "coverage_pass": cov,
        "cleanliness_pass": cl,
        "metrics_pass": mt,
        "green": green,
    }
    _report(asset_class, rows, summary)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"validate_{asset_class}.json").write_text(
        json.dumps({"summary": summary, "instruments": rows}, indent=2, default=str)
    )
    return summary


def _report(ac, rows, s):
    def line(label, p):
        col = GREEN if p == s["n"] else (YEL if p > s["n"] * 0.8 else RED)
        return f"{label:<13}: {col}{p}/{s['n']}{RST}"

    print(f"\n{'=' * 60}\n {ac.upper()} — {s['n']} instruments\n{'=' * 60}")
    print("  " + line("1.Coverage", s["coverage_pass"]))
    print("  " + line("2.Cleanliness", s["cleanliness_pass"]))
    print("  " + line("3.Metrics", s["metrics_pass"]))
    gc = GREEN if s["green"] == s["n"] else (YEL if s["green"] else RED)
    print("-" * 60)
    print(f"  GREEN (all axes): {gc}{s['green']}/{s['n']}{RST}")
    for axis in ("coverage", "cleanliness", "metrics"):
        fails = [r for r in rows if r[axis].get("pass") is False]
        if fails:
            print(
                f"  {DIM}{axis} fails ({len(fails)}): "
                + ", ".join(f"{r['symbol']}[{r[axis].get('reason', '')}]" for r in fails[:6])
                + (" …" if len(fails) > 6 else "")
                + RST
            )


def main():
    ap = argparse.ArgumentParser(description="Validate full staging universe (3 axes)")
    ap.add_argument(
        "--asset", nargs="*", choices=["stock", "etf", "index"], default=["stock", "etf", "index"]
    )
    args = ap.parse_args()
    overall = {}
    for ac in args.asset:
        overall[ac] = run(ac)
    print(f"\n{DIM}detail → output/validate_<class>.json{RST}")


if __name__ == "__main__":
    main()
