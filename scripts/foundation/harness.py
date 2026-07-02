#!/usr/bin/env python3
"""Atlas data-foundation verification harness (read-only).

The quantifiable "definition of done" from docs/atlas-data-foundation.md §5,
made runnable. Three axes, each a set of checks, evaluated PER INSTRUMENT:

  1. COVERAGE    — present in OHLCV, ≥10y deep (back to the target start or
                   listing date), enough rows for the span.
  2. CLEANLINESS — no NULL/zero/negative closes, no internal gaps vs the NSE
                   trading calendar, ≤1 trading day stale, no absurd 1-day jumps
                   (the FMCG +249.8% detector).
  3. METRICS     — TA-Lib technicals (EMA 21/50/200, RSI14, returns, RS vs
                   N50/N500 × 6 windows) present for every priced date, and a
                   recompute-and-diff matches what is stored.

Runs against the single atlas_foundation.* schema (the live data foundation).

Output: a per-axis PASS/FAIL summary + green-count to stdout, top failures with
reasons, and a full per-instrument JSON to output/. Definition of done = green
count == universe size (0 failures). Read-only: issues no writes.

Cost rule: this does the heavy lifting in Python and prints a small summary.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import _db
import numpy as np
import pandas as pd
import technicals as T

# ---------------------------------------------------------------------------
# Harness configuration (validation tolerances — NOT methodology thresholds).
# ---------------------------------------------------------------------------
COVERAGE_START = date(2016, 4, 7)  # earliest date present across the clean series
DEPTH_GRACE_DAYS = 7  # allow a few days slack vs target start
COMPLETENESS_MIN = 0.99  # ≥99% of in-span trading days must be present
STALE_MAX_TDAYS = 1  # series may lag the calendar by ≤1 trading day
JUMP_MAX_PCT = 0.50  # any |1-day move| >50% on adj close = adj error
EMA_RTOL = 1e-3  # 0.1% relative tolerance on recompute-diff
RSI_ATOL = 0.05
RET_ATOL = 1e-4
RS_ATOL = 1e-4

STAGING_SCHEMA = "atlas_foundation"
OUT_DIR = Path(__file__).resolve().parents[2] / "output"

CAL_INDEX = "NIFTY 50"  # reference series defining the NSE trading calendar
BENCHMARKS = {"n50": "NIFTY 50", "n500": "NIFTY 500"}

GREEN, RED, YEL, DIM, RST = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


# ---------------------------------------------------------------------------
# Profiles: where each role's data lives, per backend.
# ---------------------------------------------------------------------------
@dataclass
class Profile:
    name: str
    stock_ohlcv: str
    stock_close_adj: str  # adjusted close column on the OHLCV table
    index_table: str
    index_code_col: str
    index_close_col: str
    stock_tech: str | None  # technicals table (None ⇒ metrics axis all-fail)
    tech_ema_cols: dict = field(default_factory=dict)  # {21: 'ema_21', ...}
    tech_rsi_col: str | None = None
    tech_ret_cols: dict = field(default_factory=dict)  # {'1m': 'ret_1m', ...}
    tech_rs_cols: dict = field(default_factory=dict)  # {'rs_1m_n500': 'col', ...}


PROFILES: dict[str, Profile] = {
    "staging": Profile(
        name="staging",
        stock_ohlcv=f"{STAGING_SCHEMA}.ohlcv_stock",
        stock_close_adj="close_adj",
        index_table=f"{STAGING_SCHEMA}.index_prices",
        index_code_col="index_code",
        index_close_col="close",
        stock_tech=f"{STAGING_SCHEMA}.technical_daily",
        tech_ema_cols={21: "ema_21", 50: "ema_50", 200: "ema_200"},
        tech_rsi_col="rsi_14",
        tech_ret_cols={k: f"ret_{k}" for k in T.RETURN_WINDOWS},
        tech_rs_cols={f"rs_{w}_{b}": f"rs_{w}_{b}" for b in BENCHMARKS for w in T.RETURN_WINDOWS},
    ),
}


# ---------------------------------------------------------------------------
# Shared loaders
# ---------------------------------------------------------------------------
def get_calendar(p: Profile) -> pd.DatetimeIndex:
    df = _db.read_df(
        f"select date from {p.index_table} where {p.index_code_col} = :c order by date",
        {"c": CAL_INDEX},
    )
    return pd.DatetimeIndex(pd.to_datetime(df["date"]))


def load_stock_universe(symbols: list[str] | None, limit: int | None) -> pd.DataFrame:
    """Current Nifty 500 membership (is_active on instrument_master = curated universe)."""
    where = "i.asset_class = 'stock' and i.kite_token is not null and i.is_active"
    params: dict = {}
    if symbols:
        where += " and i.symbol = any(:syms)"
        params["syms"] = symbols
    sql = f"""
        select i.instrument_id, i.symbol, i.listing_date
        from atlas_foundation.instrument_master i
        where {where}
        order by i.symbol
    """
    df = _db.read_df(sql, params)
    if limit:
        df = df.head(limit)
    return df


def benchmark_series(p: Profile) -> dict[str, pd.Series]:
    out = {}
    for suf, code in BENCHMARKS.items():
        df = _db.read_df(
            f"select date, {p.index_close_col} as c from {p.index_table} "
            f"where {p.index_code_col} = :c order by date",
            {"c": code},
        )
        s = pd.Series(
            df["c"].astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(df["date"]))
        )
        out[suf] = s
    return out


# ---------------------------------------------------------------------------
# Axis 1 + 2: coverage & cleanliness (one windowed SQL aggregate, then Python)
# ---------------------------------------------------------------------------
def _covcl_aggregate(p: Profile, ids: list[str]) -> pd.DataFrame:
    """Per-instrument first/last/rows/bad_close/max_jump.

    We pull (instrument_id, date, close_adj) UNSORTED and aggregate in pandas.
    The legacy de_equity_ohlcv is year-partitioned, so a SQL window/ORDER BY
    forces a slow cross-partition sort that trips the pooler's 2-min timeout;
    sorting in pandas sidesteps that and runs identically on the clean staging
    table. Chunked by instrument batch to bound each transfer.
    """
    sql = (
        f"select instrument_id, date, {p.stock_close_adj} as cadj "
        f"from {p.stock_ohlcv} where instrument_id = any(cast(:ids as uuid[]))"
    )
    out = []
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        df = _db.read_df(sql, {"ids": chunk})
        if df.empty:
            continue
        df["instrument_id"] = df["instrument_id"].astype(str)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["instrument_id", "date"])
        df["cadj"] = pd.to_numeric(df["cadj"], errors="coerce")
        ratio = df.groupby("instrument_id")["cadj"].apply(
            lambda s: (s / s.shift(1) - 1).abs().max()
        )
        g = df.groupby("instrument_id")
        agg = pd.DataFrame(
            {
                "first_date": g["date"].min(),
                "last_date": g["date"].max(),
                "n_rows": g.size(),
                "bad_close": g["cadj"].apply(lambda s: int(((s.isna()) | (s <= 0)).sum())),
                "max_jump": ratio,
            }
        )
        out.append(agg)
    return (
        pd.concat(out)
        if out
        else pd.DataFrame(columns=["first_date", "last_date", "n_rows", "bad_close", "max_jump"])
    )


def coverage_cleanliness(p: Profile, uni: pd.DataFrame, cal: pd.DatetimeIndex) -> dict:
    ids = list(uni["instrument_id"].astype(str))
    agg = _covcl_aggregate(p, ids)
    cal_set = cal
    cal_set[-1]
    results: dict[str, dict] = {}
    for _, row in uni.iterrows():
        iid = str(row["instrument_id"])
        sym = row["symbol"]
        listing = pd.Timestamp(row["listing_date"]) if pd.notna(row["listing_date"]) else None
        r = {"symbol": sym, "coverage": {}, "cleanliness": {}}
        if iid not in agg.index:
            r["coverage"] = {"pass": False, "reason": "absent from OHLCV"}
            r["cleanliness"] = {"pass": False, "reason": "absent from OHLCV"}
            results[iid] = r
            continue
        a = agg.loc[iid]
        first_d, last_d = pd.Timestamp(a["first_date"]), pd.Timestamp(a["last_date"])
        n_rows = int(a["n_rows"])
        # target depth: back to COVERAGE_START, or listing date if later
        target_start = max(
            pd.Timestamp(COVERAGE_START),
            listing if listing is not None else pd.Timestamp(COVERAGE_START),
        )
        deep_enough = first_d <= target_start + pd.Timedelta(days=DEPTH_GRACE_DAYS)
        exp_in_span = int(((cal_set >= first_d) & (cal_set <= last_d)).sum())
        completeness = n_rows / exp_in_span if exp_in_span else 0.0
        cov_pass = deep_enough and completeness >= 0.95
        cov_reasons = []
        if not deep_enough:
            cov_reasons.append(f"starts {first_d.date()} > target {target_start.date()}")
        if completeness < 0.95:
            cov_reasons.append(f"depth {completeness:.1%} of span")
        r["coverage"] = {
            "pass": cov_pass,
            "first": str(first_d.date()),
            "rows": n_rows,
            "depth": round(completeness, 4),
            "reason": "; ".join(cov_reasons) or "ok",
        }
        # cleanliness
        bad_close = int(a["bad_close"])
        max_jump = float(a["max_jump"]) if pd.notna(a["max_jump"]) else 0.0
        stale_days = int((cal_set > last_d).sum())
        gap_complete = completeness >= COMPLETENESS_MIN
        cl_reasons = []
        if bad_close:
            cl_reasons.append(f"{bad_close} null/≤0 closes")
        if not gap_complete:
            cl_reasons.append(f"gaps: {completeness:.1%} complete")
        if stale_days > STALE_MAX_TDAYS:
            cl_reasons.append(f"stale {stale_days} tdays")
        if max_jump > JUMP_MAX_PCT:
            cl_reasons.append(f"jump {max_jump:.0%}")
        cl_pass = not cl_reasons
        r["cleanliness"] = {
            "pass": cl_pass,
            "bad_close": bad_close,
            "max_jump": round(max_jump, 4),
            "stale_tdays": stale_days,
            "reason": "; ".join(cl_reasons) or "ok",
        }
        results[iid] = r
    return results


# ---------------------------------------------------------------------------
# Axis 3: metrics — recompute via TA-Lib and diff vs stored
# ---------------------------------------------------------------------------
def metrics_axis(
    p: Profile, uni: pd.DataFrame, benches: dict[str, pd.Series], sample: int | None
) -> dict:
    out: dict[str, dict] = {}
    subset = uni if sample is None else uni.head(sample)
    for _, row in subset.iterrows():
        iid, sym = str(row["instrument_id"]), row["symbol"]
        out[iid] = _metrics_one(p, iid, sym, benches)
    return out


def _metrics_one(p: Profile, iid: str, sym: str, benches: dict[str, pd.Series]) -> dict:
    checks: list[tuple[str, bool, str]] = []
    if not p.stock_tech:
        return {
            "symbol": sym,
            "pass": False,
            "sampled": True,
            "checks": [["technicals table", False, "no technicals table"]],
        }
    px = _db.read_df(
        f"select date, {p.stock_close_adj} as c from {p.stock_ohlcv} "
        "where instrument_id = cast(:i as uuid) order by date",
        {"i": iid},
    )
    if len(px) < T.EMA_PERIODS[-1] + 5:
        return {
            "symbol": sym,
            "pass": False,
            "sampled": True,
            "checks": [["history", False, f"only {len(px)} rows"]],
        }
    close = pd.Series(
        px["c"].astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(px["date"]))
    )
    recomp = T.compute_price_technicals(close)
    for suf in BENCHMARKS:
        recomp = recomp.join(T.compute_relative_strength(close, benches[suf], suf))

    stored = _db.read_df(
        f"select * from {p.stock_tech} where instrument_id = cast(:i as uuid) order by date",
        {"i": iid},
    )
    stored.index = pd.DatetimeIndex(pd.to_datetime(stored["date"]))

    # EMA 21/50/200
    for period in T.EMA_PERIODS:
        col = p.tech_ema_cols.get(period)
        if not col:
            checks.append((f"ema_{period}", False, "column absent"))
            continue
        checks.append(
            _diff_check(f"ema_{period}", recomp[f"ema_{period}"], stored.get(col), rtol=EMA_RTOL)
        )
    # RSI
    if p.tech_rsi_col:
        checks.append(
            _diff_check("rsi_14", recomp["rsi_14"], stored.get(p.tech_rsi_col), atol=RSI_ATOL)
        )
    else:
        checks.append(("rsi_14", False, "column absent"))
    # returns
    for w in T.RETURN_WINDOWS:
        col = p.tech_ret_cols.get(w)
        if not col:
            checks.append((f"ret_{w}", False, "column absent"))
            continue
        checks.append(_diff_check(f"ret_{w}", recomp[f"ret_{w}"], stored.get(col), atol=RET_ATOL))
    # RS (N50/N500 × 6 windows)
    for suf in BENCHMARKS:
        for w in T.RETURN_WINDOWS:
            key = f"rs_{w}_{suf}"
            col = p.tech_rs_cols.get(key)
            if not col:
                checks.append((key, False, "column absent"))
                continue
            checks.append(_diff_check(key, recomp[key], stored.get(col), atol=RS_ATOL))

    passed = all(ok for _, ok, _ in checks)
    return {
        "symbol": sym,
        "pass": passed,
        "sampled": True,
        "checks": [[n, ok, msg] for n, ok, msg in checks],
    }


def _diff_check(
    name: str, recomp: pd.Series, stored: pd.Series | None, rtol: float = 0.0, atol: float = 0.0
) -> tuple[str, bool, str]:
    """Compare recomputed vs stored on overlapping, both-non-NaN dates."""
    if stored is None:
        return (name, False, "column absent")
    a = recomp.dropna()
    b = pd.to_numeric(stored, errors="coerce").reindex(recomp.index).dropna()
    idx = a.index.intersection(b.index)
    if len(idx) == 0:
        return (name, False, "no overlapping non-null dates")
    av, bv = a.loc[idx].to_numpy(), b.loc[idx].to_numpy()
    tol = atol + rtol * np.abs(bv)
    diff = np.abs(av - bv)
    nbad = int((diff > tol).sum())
    if nbad == 0:
        return (name, True, f"matches on {len(idx)} dates")
    worst = float(np.nanmax(diff))
    return (name, False, f"{nbad}/{len(idx)} mismatch (worst Δ={worst:.4g})")


# ---------------------------------------------------------------------------
# Orchestration + reporting
# ---------------------------------------------------------------------------
def run(
    profile: str, symbols: list[str] | None, limit: int | None, metrics_sample: int | None
) -> dict:
    p = PROFILES[profile]
    cal = get_calendar(p)
    uni = load_stock_universe(symbols, limit)
    benches = benchmark_series(p)
    print(
        f"{DIM}profile={profile} universe=stocks members={len(uni)} "
        f"calendar={len(cal)} tdays [{cal[0].date()}..{cal[-1].date()}]{RST}"
    )

    covcl = coverage_cleanliness(p, uni, cal)
    met = metrics_axis(p, uni, benches, metrics_sample)

    rows = []
    for _, u in uni.iterrows():
        iid, sym = str(u["instrument_id"]), u["symbol"]
        cc = covcl.get(iid, {})
        m = met.get(iid)
        rows.append(
            {
                "instrument_id": iid,
                "symbol": sym,
                "coverage": cc.get("coverage", {}),
                "cleanliness": cc.get("cleanliness", {}),
                "metrics": m or {"pass": None, "sampled": False},
            }
        )
    summary = _summarize(profile, rows, metrics_sample, len(uni))
    _report(profile, rows, summary)
    return summary


def _summarize(profile, rows, metrics_sample, n_uni) -> dict:
    def axis_pass(r, axis):
        return bool(r[axis].get("pass"))

    cov_pass = sum(axis_pass(r, "coverage") for r in rows)
    cl_pass = sum(axis_pass(r, "cleanliness") for r in rows)
    met_rows = [r for r in rows if r["metrics"].get("sampled")]
    met_pass = sum(bool(r["metrics"].get("pass")) for r in met_rows)
    green = sum(
        1
        for r in rows
        if axis_pass(r, "coverage")
        and axis_pass(r, "cleanliness")
        and (r["metrics"].get("pass") if r["metrics"].get("sampled") else False)
    )
    return {
        "profile": profile,
        "universe_size": n_uni,
        "coverage": {"pass": cov_pass, "fail": n_uni - cov_pass, "total": n_uni},
        "cleanliness": {"pass": cl_pass, "fail": n_uni - cl_pass, "total": n_uni},
        "metrics": {
            "pass": met_pass,
            "fail": len(met_rows) - met_pass,
            "total": len(met_rows),
            "sampled": metrics_sample is not None,
        },
        "green_count": green,
        "all_green": green == n_uni,
    }


def _report(profile, rows, summary):
    def bar(d):
        return f"{GREEN if d['fail'] == 0 else RED}{d['pass']}/{d['total']} pass{RST}" + (
            f" {RED}{d['fail']} fail{RST}" if d["fail"] else ""
        )

    print("\n" + "=" * 64)
    print(f" AXIS SUMMARY — profile={profile}")
    print("=" * 64)
    print(f"  1. Coverage    : {bar(summary['coverage'])}")
    print(f"  2. Cleanliness : {bar(summary['cleanliness'])}")
    msfx = " (sampled)" if summary["metrics"]["sampled"] else ""
    print(f"  3. Metrics{msfx:<6}: {bar(summary['metrics'])}")
    gc, n = summary["green_count"], summary["universe_size"]
    col = GREEN if summary["all_green"] else (YEL if gc else RED)
    print("-" * 64)
    print(
        f"  GREEN (all axes): {col}{gc}/{n}{RST}   "
        f"{'✅ ALL GREEN' if summary['all_green'] else '❌ not yet green'}"
    )
    print("=" * 64)

    for axis in ("coverage", "cleanliness", "metrics"):
        fails = [
            r
            for r in rows
            if (r[axis].get("pass") is False) and (axis != "metrics" or r["metrics"].get("sampled"))
        ]
        if not fails:
            continue
        print(f"\n  top {axis} failures ({len(fails)}):")
        for r in fails[:10]:
            if axis == "metrics":
                bad = [f"{n}:{msg}" for n, ok, msg in r["metrics"].get("checks", []) if not ok]
                reason = "; ".join(bad[:4]) + (" …" if len(bad) > 4 else "")
            else:
                reason = r[axis].get("reason", "")
            print(f"    {RED}✗{RST} {r['symbol']:<14} {DIM}{reason}{RST}")
        if len(fails) > 10:
            print(f"    {DIM}… +{len(fails) - 10} more (see JSON){RST}")

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"foundation_harness_{profile}.json"
    out.write_text(json.dumps({"summary": summary, "instruments": rows}, indent=2, default=str))
    print(f"\n  {DIM}full per-instrument detail → {out}{RST}")


def main():
    ap = argparse.ArgumentParser(description="Atlas data-foundation harness")
    ap.add_argument("--profile", choices=list(PROFILES), default="staging")
    ap.add_argument("--symbols", nargs="*", help="restrict to these NSE symbols")
    ap.add_argument("--limit", type=int, help="cap universe size")
    ap.add_argument(
        "--metrics-sample",
        type=int,
        default=None,
        help="run metrics axis on first N instruments (default: all)",
    )
    args = ap.parse_args()
    run(args.profile, args.symbols, args.limit, args.metrics_sample)


if __name__ == "__main__":
    main()
