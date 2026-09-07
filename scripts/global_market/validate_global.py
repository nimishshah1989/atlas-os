#!/usr/bin/env python3
"""INDEPENDENT output gate for the US platform — the Gate pattern from validate_lenses.py.

Every assertion here queries REAL produced output or a REAL feed (rule #0). The Phase 1–3
definitions of done (checks A–E in the plan) are added here in the PR that lands each
phase's producers; a check that does not exist yet is not a choice, so an orchestrator
cannot wire it early and fail (or pass) vacuously.

    python scripts/global_market/validate_global.py --check SIP [--stooq-file SPY.US.txt]
    python scripts/global_market/validate_global.py --check BASIS

--check SIP — the Phase 0 gate (result recorded in docs/global/data-sources.md):
  One pull of SPY / AAPL / QQQ daily bars, ``adjustment="raw"`` and ``feed=sip``, over the
  last SIP_LOOKBACK_DAYS calendar days (raw, because FRED's SP500 is a price index and
  Stooq's volume is unadjusted — the comparisons below need like for like).
  (0) SPY has ≥ SIP_SESSIONS sessions in the window; AAPL and QQQ have a bar on every one.
  (1) Pearson correlation of SPY daily returns vs FRED SP500 daily returns on the overlap
      ≥ SIP_MIN_RETURN_CORR — proves the bars are SPY at all.
  (2) median(Alpaca SPY volume ÷ Stooq SPY volume) on overlapping sessions within
      SIP_VOLUME_RATIO_BAND — the check that actually discriminates SIP from IEX-only
      (IEX prints ~2–3% of consolidated volume). Needs --stooq-file; without it the
      check FAILS as "not run" — an inconclusive gate must not read as PASS.
  (3) no session in the FRED (and Stooq) calendar missing from Alpaca.

--check BASIS — WHICH price series ``ohlcv_daily.close`` actually carries. The archive
  arrives with ``adjustment_source='stooq:unknown'``: Stooq documents no adjustment policy,
  so the basis has to be MEASURED, not assumed, before anything downstream divides by it.
  FRED's ``SP500`` is the independent witness — a PRICE index (no dividends), from a
  publisher with no relationship to Stooq, reachable with no key.
  (0) enough overlapping sessions for the statistics to be evidence at all.
  (1) daily-return correlation ≥ BASIS_MIN_RETURN_CORR — proves the rows are an S&P 500
      tracker, i.e. that the comparison is like for like. It cannot say more: a raw feed and
      a back-adjusted feed of the SAME fund have almost identical daily returns.
  (2) the LEVEL ratio (close ÷ index) walks one way (rank correlation with time ≥
      BASIS_MIN_RATIO_TREND) and ends within BASIS_SPOT_RATIO_TOL of SPY's structural
      BASIS_SPOT_RATIO — past prices depressed relative to the index and converging to spot
      today is the shape of a back-adjustment re-based to the download date.
  (3) THE DISCRIMINATOR: the annualised excess of the archive's CAGR over the price index's
      sits inside BASIS_CAGR_EXCESS_BAND, a dividend yield. Checks (1) and (2) cannot tell
      dividends from any other one-way drift; only the MAGNITUDE can, and a split-only
      series (real traded prices, no dividend adjustment) reads ≈ 0 there.
  Prints a one-line VERDICT naming the detected basis — ``total_return`` or ``split_only``,
  or ``indeterminate`` when the evidence names neither, which FAILS rather than guessing.
Writes nothing. Exit 0 iff every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atlas.global_market import calendar as gcal

# ── What "consolidated" means. A DATA-QUALITY definition (is this feed the feed we think
# it is?), not methodology: no score, weight or universe cut depends on these numbers. ──
SIP_SESSIONS = 40
SIP_MIN_RETURN_CORR = 0.999
SIP_VOLUME_RATIO_BAND = (0.9, 1.1)
SIP_MIN_OVERLAP = 10  # fewer overlapping points than this is no evidence either way
SIP_LOOKBACK_DAYS = 70  # calendar days that comfortably contain 40 sessions
SIP_SYMBOLS = ("SPY", "AAPL", "QQQ")

# ── What the stored price column CARRIES. Same category as the SIP constants above: a
# DATA-QUALITY definition (which series is in `close`?), not methodology — no score, weight
# or universe cut reads any of these. Each is justified against the measurement the gate
# itself prints, taken 2026-09-07 over 2,513 overlapping sessions (2016-09-06 → 2026-09-03)
# of the Stooq archive vs FRED SP500: return correlation 0.998352, ratio 0.086514 → 0.099793
# with rank-vs-time 0.99712, CAGR 15.134% vs 13.500% → excess 1.634%/yr. ──
BASIS_SYMBOL = "SPY"
BASIS_INDEX_SERIES = "SP500"
# ≈4 years of sessions. The measured overlap is 2,513 and FRED publishes SP500 as a rolling
# ten-year window, so this can only bind on a partial archive. Below ~4 years a 1.6%/yr
# dividend signal stops separating cleanly from SPY-vs-index tracking noise, and check (3)
# would be measuring nothing.
BASIS_MIN_SESSIONS = 1000
# Measured 0.998352. Everything else in the archive is far below: QQQ 0.918, DIA 0.846,
# IWM 0.840, XLK 0.841, AAPL 0.332 against the same index over the same feed. 0.99 sits
# clear of the measurement and clear of every non-S&P-500 series.
BASIS_MIN_RETURN_CORR = 0.99
# Rank correlation of the level ratio with time. A back-adjustment scales every past bar by
# the dividends paid SINCE it, which is mechanically monotone — measured 0.99712. A
# split-only series has no such drift and reads near 0.
BASIS_MIN_RATIO_TREND = 0.90
# SPY is structured at ~1/10 of the S&P 500 index; a bar that needed no adjustment (the
# newest one) must therefore sit there. Measured last ratio 0.099793 — 0.21% off — so the
# 2% tolerance is ~10x the observed deviation, wide enough for the accrued-dividend and
# expense-drag wobble (< 1% historically) and far too tight for a differently-based series.
BASIS_SPOT_RATIO = 0.10
BASIS_SPOT_RATIO_TOL = 0.02
# The dividend band, on the ARITHMETIC difference of the two CAGRs (15.134% − 13.500% =
# 1.634%/yr). Note that is not the textbook yield: the ratio walk annualises to the
# GEOMETRIC excess, 1.4396%/yr, and the arithmetic figure is that times (1 + index CAGR).
# The band is drawn around the arithmetic number because that is what the gate reports.
# SPY's trailing yield has run ~1.2–2.2% over the last decade, so both readings sit inside.
# The floor (0.8%) is half the measurement and ~8x SPY's expense drag (0.0945%/yr, the only
# drift a split-only series can show); the ceiling (3.0%) is below a double-counted
# adjustment (~3.3%) while leaving room for a higher-yield decade.
BASIS_CAGR_EXCESS_BAND = (0.008, 0.030)
# Below this the dividends are demonstrably NOT in the series. The gap to the band's floor
# is deliberate: between 0.4% and 0.8% the evidence names neither basis, and the gate says
# `indeterminate` and fails rather than choosing one.
BASIS_SPLIT_ONLY_MAX_CAGR_EXCESS = 0.004
BASIS_DAYS_PER_YEAR = 365.25  # calendar years for the CAGR exponent, leap years included


class Gate:
    def __init__(self) -> None:
        self.fails = 0

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        tag = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        print(f"  [{tag}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            self.fails += 1
        return ok


def read_stooq(path: Path) -> pd.DataFrame:
    """Stooq daily file → DataFrame[date, close, volume].

    Format: ``<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>``
    with DATE as YYYYMMDD; only PER == D rows are daily bars.
    """
    df = pd.read_csv(path)
    df.columns = [str(c).strip().strip("<>").lower() for c in df.columns]
    need = {"ticker", "per", "date", "close", "vol"}
    if not need <= set(df.columns):
        raise ValueError(f"{path}: not a Stooq daily file (columns {list(df.columns)})")
    daily = df.loc[df["per"].astype(str).str.upper() == "D"]
    out = pd.DataFrame(
        {
            "date": [datetime.strptime(str(d), "%Y%m%d").date() for d in daily["date"]],
            "close": daily["close"].astype(float).to_list(),
            "volume": daily["vol"].astype("int64").to_list(),
        }
    )
    return out.sort_values(by="date", ignore_index=True)


def _returns_on_overlap(spy: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    m = spy[["date", "close"]].merge(fred, on="date", how="inner").sort_values("date")
    m["r_spy"] = m["close"].astype(float).pct_change()
    m["r_idx"] = m["value"].astype(float).pct_change()
    return m.dropna(subset=["r_spy", "r_idx"]).reset_index(drop=True)


def check_SIP(g: Gate, stooq_file: str | None) -> None:
    print("== SIP gate: is Alpaca's free-plan feed consolidated (SIP) or IEX-only? ==")
    # Lazy: config needs atlas.config.MARKETS; the not-implemented checks must not.
    from atlas.global_market.config import alpaca_keys, fred_key

    try:
        keys = alpaca_keys()
        fkey = fred_key()
    except RuntimeError as e:
        g.check("credentials present", False, str(e))
        return
    from atlas.global_market.providers.alpaca import AlpacaProvider
    from atlas.global_market.providers.fred import fred_series

    end = gcal.eod_cutoff(datetime.now(UTC))
    start = end - timedelta(days=SIP_LOOKBACK_DAYS)
    provider = AlpacaProvider(keys=keys)
    bars = provider.bars(SIP_SYMBOLS, start, end, adjustment="raw")
    per = {s: bars.loc[bars["symbol"] == s].sort_values(by="date") for s in SIP_SYMBOLS}
    for s, df in per.items():
        span = f"{df['date'].min()} → {df['date'].max()}" if len(df) else "none"
        n_calls = sum(provider.calls.values())
        print(f"  {s}: {len(df)} daily bars ({span}), {n_calls} request(s) so far")

    spy = per["SPY"].tail(SIP_SESSIONS).reset_index(drop=True)
    g.check(
        f"SPY has ≥ {SIP_SESSIONS} sessions in the last {SIP_LOOKBACK_DAYS} calendar days",
        len(spy) >= SIP_SESSIONS,
        f"{len(spy)} sessions",
    )
    if spy.empty:
        return
    first: date = spy["date"].iloc[0]  # spy is sorted ascending by date
    last: date = spy["date"].iloc[-1]
    spy_dates = set(spy["date"])
    for s in ("AAPL", "QQQ"):
        got = set(per[s]["date"])
        g.check(
            f"{s} has a bar on every SPY session",
            spy_dates <= got,
            f"{len(spy_dates - got)} SPY session(s) missing for {s}",
        )

    # (1) same index, two feeds: daily returns must agree almost perfectly.
    fred = fred_series("SP500", first - timedelta(days=7), fkey, end=last)
    m = _returns_on_overlap(spy, fred)
    r_spy = m["r_spy"].to_numpy(dtype=float)
    r_idx = m["r_idx"].to_numpy(dtype=float)
    corr = float(np.corrcoef(r_spy, r_idx)[0, 1]) if len(m) >= 2 else float("nan")  # Pearson
    detail = f"r={corr:.5f} on {len(m)} overlapping daily returns"
    if len(m):
        resid = (m["r_spy"] - m["r_idx"]).abs()
        i = int(resid.idxmax())
        detail += (
            f"; worst residual {resid[i]:.4%} on {m['date'][i]} (an SPY ex-dividend day shows here)"
        )
    g.check(
        f"(1) SPY daily-return correlation vs FRED SP500 ≥ {SIP_MIN_RETURN_CORR}",
        len(m) >= SIP_MIN_OVERLAP and corr >= SIP_MIN_RETURN_CORR,
        detail,
    )

    # (3) calendar: every FRED session in Alpaca's span must be an Alpaca session.
    fred_dates = {d for d in fred["date"] if first <= d <= last}
    missing = sorted(fred_dates - spy_dates)
    g.check(
        "(3) no FRED session missing from Alpaca",
        bool(fred_dates) and not missing,
        f"{len(missing)} missing of {len(fred_dates)} FRED sessions: {missing[:5]}"
        if missing
        else f"{len(fred_dates)} FRED sessions all present",
    )

    # (2) volume: the discriminator. IEX-only ≈ 0.02–0.03 of consolidated.
    if not stooq_file:
        g.check(
            f"(2) median Alpaca/Stooq SPY volume ratio in {SIP_VOLUME_RATIO_BAND}",
            False,
            "NOT RUN — pass --stooq-file SPY.US.txt (from Stooq d_us_txt.zip); the "
            "correlation check alone cannot tell IEX from SIP, so this gate is inconclusive",
        )
        return
    st = read_stooq(Path(stooq_file))
    j = spy[["date", "volume", "close"]].merge(st, on="date", suffixes=("_alpaca", "_stooq"))
    lo, hi = SIP_VOLUME_RATIO_BAND
    if len(j) < SIP_MIN_OVERLAP:
        g.check(
            f"(2) median Alpaca/Stooq SPY volume ratio in {SIP_VOLUME_RATIO_BAND}",
            False,
            f"only {len(j)} overlapping sessions with {stooq_file} (Stooq spans "
            f"{st['date'].min()} → {st['date'].max()}); need ≥ {SIP_MIN_OVERLAP}",
        )
        return
    ratio = j["volume_alpaca"].astype(float) / j["volume_stooq"].astype(float)
    med = float(ratio.median())
    close_diff = ((j["close_alpaca"].astype(float) / j["close_stooq"]) - 1).abs().median()
    g.check(
        f"(2) median Alpaca/Stooq SPY volume ratio in {SIP_VOLUME_RATIO_BAND}",
        lo <= med <= hi,
        f"median={med:.4f} over {len(j)} sessions (min {ratio.min():.4f}, max {ratio.max():.4f}); "
        f"median |close diff| {float(close_diff):.4%}; IEX-only would read ~0.02–0.03",
    )
    st_dates = {d for d in st["date"] if first <= d <= last}
    st_missing = sorted(st_dates - spy_dates)
    g.check(
        "(3b) no Stooq session missing from Alpaca",
        bool(st_dates) and not st_missing,
        f"{len(st_missing)} missing: {st_missing[:5]}"
        if st_missing
        else f"{len(st_dates)} Stooq sessions all present",
    )


def _cagr(first: float, last: float, years: float) -> float:
    return (last / first) ** (1.0 / years) - 1.0


def _rank_trend(values: pd.Series) -> float:
    """Spearman rank correlation of ``values`` with its own (already time-ordered) position.

    Rank correlation, not Pearson: back-adjustment guarantees the ratio walks ONE WAY, not
    that it walks in a straight line, and a rank measure says exactly that without assuming
    the shape. ``method="spearman"`` is pandas' own — no ranking by hand, and no extra
    dependency either; it returns NaN for the zero-variance ratio that never moves, which is
    the answer (no trend) and fails the floor.
    """
    position = pd.Series(np.arange(len(values), dtype=float), index=values.index)
    return float(values.corr(position, method="spearman"))


def basis_verdict(cagr_excess: float, trend: float) -> str:
    """The detected price basis, from the two measurements that can tell them apart.

    ``indeterminate`` is a real answer, not a fallback: between the split-only ceiling and
    the dividend band the evidence names NEITHER basis, and a gate that picked one in order
    to be able to pass would be exactly the inconclusive-reads-as-PASS failure this file
    exists to prevent.
    """
    lo, hi = BASIS_CAGR_EXCESS_BAND
    if trend >= BASIS_MIN_RATIO_TREND and lo <= cagr_excess <= hi:
        return "total_return"
    if cagr_excess <= BASIS_SPLIT_ONLY_MAX_CAGR_EXCESS:
        return "split_only"
    return "indeterminate"


def check_BASIS(g: Gate) -> None:
    print(f"== BASIS gate: what price series does {_gdb_schema()}.ohlcv_daily carry? ==")
    # Lazy, as check_SIP is: a gate that is not the one being run must not need a DB URL.
    import _gdb

    from atlas.global_market.providers.fred import fred_series

    # Floats below are STATISTICS (correlations, a CAGR), never money: `close` is numeric in
    # Postgres and stays Decimal everywhere it is stored or displayed.
    bars = _gdb.read_df(
        f"select date, close from {_gdb.M}.ohlcv_daily where instrument_id = "
        f"(select instrument_id from {_gdb.M}.instrument_master "
        "where symbol = :sym and is_active) and close is not null order by date",
        {"sym": BASIS_SYMBOL},
    )
    if bars.empty:
        g.check(f"{BASIS_SYMBOL} has bars in ohlcv_daily", False, "no rows — nothing to measure")
        return
    print(
        f"  {BASIS_SYMBOL}: {len(bars):,d} bars {bars['date'].iloc[0]} → {bars['date'].iloc[-1]}"
        f" from {_gdb.M}.ohlcv_daily"
    )

    first: date = bars["date"].iloc[0]
    last: date = bars["date"].iloc[-1]
    index = fred_series(BASIS_INDEX_SERIES, first, None, end=last)  # keyless: no FRED_API_KEY
    print(
        f"  FRED {BASIS_INDEX_SERIES}: {len(index):,d} observations "
        f"{index['date'].iloc[0] if len(index) else '—'} → "
        f"{index['date'].iloc[-1] if len(index) else '—'} (keyless CSV export)"
    )

    m = bars.merge(index, on="date", how="inner").sort_values("date", ignore_index=True)
    n = len(m)
    span_years = (m["date"].iloc[-1] - m["date"].iloc[0]).days / BASIS_DAYS_PER_YEAR if n else 0.0
    ok_n = g.check(
        f"(0) ≥ {BASIS_MIN_SESSIONS:,d} sessions overlap {BASIS_SYMBOL} and FRED "
        f"{BASIS_INDEX_SERIES}",
        n >= BASIS_MIN_SESSIONS,
        f"{n:,d} sessions"
        + (
            f" {m['date'].iloc[0]} → {m['date'].iloc[-1]} ({span_years:.2f} years)"
            if n
            else " — no overlap, so nothing below is evidence"
        ),
    )
    if not ok_n:
        print("\n  VERDICT: basis=UNKNOWN — too little overlap to measure; no basis claimed")
        return

    # (1) the rows are an S&P 500 tracker at all.
    px = m["close"].astype(float)
    ix = m["value"].astype(float)
    r = pd.DataFrame({"a": px.pct_change(), "b": ix.pct_change()}).dropna()
    corr = float(np.corrcoef(r["a"], r["b"])[0, 1])
    g.check(
        f"(1) daily-return correlation vs FRED {BASIS_INDEX_SERIES} ≥ {BASIS_MIN_RETURN_CORR}",
        corr >= BASIS_MIN_RETURN_CORR,
        f"r={corr:.6f} on {len(r):,d} daily returns",
    )

    # (2) the level ratio walks one way and lands on spot.
    ratio = px / ix
    trend = _rank_trend(ratio)
    spot_dev = abs(float(ratio.iloc[-1]) / BASIS_SPOT_RATIO - 1.0)
    g.check(
        f"(2a) level ratio rank-correlates with time ≥ {BASIS_MIN_RATIO_TREND}",
        trend >= BASIS_MIN_RATIO_TREND,
        f"rho={trend:.5f}; ratio {float(ratio.iloc[0]):.6f} → {float(ratio.iloc[-1]):.6f} "
        f"({float(ratio.iloc[-1]) / float(ratio.iloc[0]) - 1:+.2%} over the span)",
    )
    g.check(
        f"(2b) newest ratio is spot: within {BASIS_SPOT_RATIO_TOL:.0%} of "
        f"{BASIS_SYMBOL}'s structural {BASIS_SPOT_RATIO}",
        spot_dev <= BASIS_SPOT_RATIO_TOL,
        f"{float(ratio.iloc[-1]):.6f} on {m['date'].iloc[-1]} — {spot_dev:.3%} off",
    )

    # (3) the discriminator: the drift is the size of a dividend yield.
    cagr_px = _cagr(float(px.iloc[0]), float(px.iloc[-1]), span_years)
    cagr_ix = _cagr(float(ix.iloc[0]), float(ix.iloc[-1]), span_years)
    excess = cagr_px - cagr_ix
    lo, hi = BASIS_CAGR_EXCESS_BAND
    g.check(
        f"(3) CAGR excess over the price index inside {lo:.1%}–{hi:.1%} (a dividend yield)",
        lo <= excess <= hi,
        f"{BASIS_SYMBOL} {cagr_px:.3%}/yr vs {BASIS_INDEX_SERIES} {cagr_ix:.3%}/yr → "
        f"excess {excess:+.3%}/yr over {span_years:.2f} years; split-only reads ≈ 0",
    )

    basis = basis_verdict(excess, trend)
    g.check(
        "(4) the measured basis is total_return",
        basis == "total_return",
        f"detected {basis}"
        + (
            " — ohlcv_daily.close holds REAL TRADED PRICES with no dividend adjustment; "
            "anything downstream that assumed total return is WRONG"
            if basis == "split_only"
            else ""
            if basis == "total_return"
            else " — the evidence names neither basis; do not assume one"
        ),
    )
    reading = (
        "dividend back-adjusted (total return), re-based to the download date"
        if basis == "total_return"
        else "NOT the total-return series this pipeline expects"
    )
    print(
        f"\n  VERDICT: basis={basis} — {BASIS_SYMBOL} close is {reading} "
        f"[r={corr:.6f}, rho={trend:.5f}, excess={excess:+.3%}/yr, n={n:,d}]"
    )


def _gdb_schema() -> str:
    """The global schema name, for the banner — without importing ``_gdb`` at module level."""
    from atlas.global_market.config import CONFIG

    return CONFIG.schema


def main() -> None:
    ap = argparse.ArgumentParser(description="US-platform output gates (rule #0: real data only)")
    ap.add_argument("--check", choices=["SIP", "BASIS"], required=True)
    ap.add_argument(
        "--stooq-file",
        default=None,
        help="Stooq SPY.US.txt (from d_us_txt.zip) for the SIP volume-ratio discriminator",
    )
    args = ap.parse_args()
    g = Gate()
    try:
        if args.check == "SIP":
            check_SIP(g, args.stooq_file)
        else:
            check_BASIS(g)
    except Exception as e:
        print(f"  \033[31mFAIL\033[0m gate raised: {e!r}")
        g.fails += 1
    verdict = (
        f"✅ {args.check} GATE PASS"
        if g.fails == 0
        else f"❌ {args.check} GATE FAIL — {g.fails} check(s) failed"
    )
    print(f"\n{verdict}")
    sys.exit(0 if g.fails == 0 else 1)


if __name__ == "__main__":
    main()
