#!/usr/bin/env python3
"""INDEPENDENT output gate for the US platform — the Gate pattern from validate_lenses.py.

Every assertion here queries REAL produced output or a REAL feed (rule #0). The Phase 1–3
definitions of done (checks A–E in the plan) are added here in the PR that lands each
phase's producers; a check that does not exist yet is not a choice, so an orchestrator
cannot wire it early and fail (or pass) vacuously.

    python scripts/global_market/validate_global.py --check SIP [--stooq-file SPY.US.txt]

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


def main() -> None:
    ap = argparse.ArgumentParser(description="US-platform output gates (rule #0: real data only)")
    ap.add_argument("--check", choices=["SIP"], required=True)
    ap.add_argument(
        "--stooq-file",
        default=None,
        help="Stooq SPY.US.txt (from d_us_txt.zip) for the SIP volume-ratio discriminator",
    )
    args = ap.parse_args()
    g = Gate()
    try:
        check_SIP(g, args.stooq_file)
    except Exception as e:
        print(f"  \033[31mFAIL\033[0m gate raised: {e!r}")
        g.fails += 1
    print(
        f"\n{'✅ SIP GATE PASS' if g.fails == 0 else f'❌ SIP GATE FAIL — {g.fails} check(s) failed'}"
    )
    sys.exit(0 if g.fails == 0 else 1)


if __name__ == "__main__":
    main()
