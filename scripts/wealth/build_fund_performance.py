"""Per-fund performance engine — Prompt 5 of the seven-prompt MF audit.

One row per HELD EQUITY fund (a wealth.schemes row with asset_class='Equity'
and >=1 wealth.holdings row) in wealth.fund_performance:

  roll_3y_pct / roll_5y_pct  annualised CAGR over the trailing 3y / 5y,
      CALENDAR-ANCHORED to the book's as-of date and smoothed across 12 monthly
      rolling windows (mean of the per-anchor CAGRs) instead of one noisy
      point-to-point reading. roll_5y is NULL (verdict='insufficient_history')
      when the fund lacks a full 5y of NAV reaching the as-of date.
  dn_capture_pct  the fund's decline vs the market's decline through the three
      DEEPEST market drawdowns (peak->trough) the fund lived through. Windows,
      troughs and the market denominator all come from ONE series — the
      BENCH_ID Nifty-50 index-fund NAV that drawdown_windows() is defined on —
      so the ratio is internally consistent (using index_prices' price-return
      NIFTY 50 would mismatch the series the windows were carved from). <100%
      = the fund fell less than the market = protected on the downside.
  best_year_stripped_pct  full-period annualised return with the single best
      rolling-12m window removed, re-annualised over (life - 1y): the
      "one lucky year" test. best_year_stripped <= full_period for any fund up
      over its life.
  full_period_pct  annualised CAGR over the fund's entire NAV history.
  beat_count / windows  over up to 20 trailing rolling-1y windows, how many the
      fund beat its benchmark index (and how many windows were evaluable).
      primary_benchmark (Morningstar text) is mapped to the nearest NSE
      index_code; these are NSE PRICE-return indices vs the funds' TOTAL-return
      benchmarks, so benchmark_note flags the approximation. No mappable
      benchmark -> both legs NULL, note explains.

verdict: 'scored' | 'insufficient_history'. benchmark_note carries the
benchmark-mapping caveat plus any history caveat (short / stale).

Usage: set -a; source .env; set +a; .venv/bin/python scripts/wealth/build_fund_performance.py
"""

from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd
from behaviour_fingerprints import drawdown_windows
from engine_common import BENCH_ID, NavLookup, connect, nav_series
from psycopg2.extras import execute_values

FRESH_DAYS = 45          # a fund is "current" if its last NAV is within this of as-of
N_ROLL_ANCHORS = 12      # trailing monthly anchors averaged for roll_3y / roll_5y
N_BEAT_WINDOWS = 20      # trailing monthly-spaced rolling-1y windows for beat_count
WORST_N = 3              # deepest market drawdowns used for dn_capture

# primary_benchmark (Morningstar text) -> (NSE index_code, kind).
#   'direct' = the same Nifty index family exists in atlas_foundation.index_prices.
#   'proxy'  = the benchmark is a non-NSE (BSE / vendor) index with no NSE twin;
#              mapped to the nearest NSE index by construction (breadth/segment).
# EVERY mapped leg is an NSE PRICE-return index vs the fund's TOTAL-return
# benchmark, so all mapped rows carry the price-vs-TR caveat in benchmark_note.
# NOTE ON index_code CHOICE: several Nifty indices exist under TWO codes in
# index_prices — a recently re-ingested full-name series with only ~3 days of
# data, and NSE's canonical abbreviated series with ~20y. We map to the
# DEEP-history code (e.g. 'NIFTY SMLCAP 250', not the 20-day 'NIFTY SMALLCAP
# 250'), else 62 funds' benchmark legs would be spuriously NULL.
BENCHMARK_MAP = {
    "Nifty Midcap 150 TR INR":            ("NIFTY MIDCAP 150", "direct"),
    "Nifty LargeMidcap 250 TR INR":       ("NIFTY LARGEMID250", "direct"),
    "Nifty Smallcap 250 TR INR":          ("NIFTY SMLCAP 250", "direct"),
    "Nifty 500 Multicap 50:25:25 TR INR": ("NIFTY500 MULTICAP", "direct"),
    "Nifty Infrastructure TR INR":        ("NIFTY INFRA", "direct"),
    "Nifty Financial Services TR INR":    ("NIFTY FIN SERVICE", "direct"),
    "Nifty IT TR INR":                    ("NIFTY IT", "direct"),
    "Nifty Energy TR INR":                ("NIFTY ENERGY", "direct"),
    "BSE 500 India TR INR":               ("NIFTY 500", "proxy"),   # broad ~500 name
    "BSE 100 India TR INR":               ("NIFTY 100", "proxy"),   # large-cap 100
    "BSE Healthcare PR INR":              ("NIFTY HEALTHCARE", "proxy"),
}

MONTH = pd.DateOffset(months=1)
YEAR = pd.DateOffset(years=1)
FRESH = pd.Timedelta(days=FRESH_DAYS)


def _pct(x: float | None) -> float | None:
    """Fraction -> rounded percentage, dropping any NaN/Inf (never leaks to DB)."""
    if x is None or not math.isfinite(x):
        return None
    return round(x * 100.0, 2)


def _bulk_navs(conn, mstar_ids: list[str]) -> dict[str, pd.Series]:
    """Same semantics as engine_common.nav_series (nav>0, dedup last, sorted,
    float) but one round trip for the whole held-equity universe."""
    df = pd.read_sql(
        "select mstar_id, nav_date, nav::float nav from atlas_foundation.de_mf_nav_daily "
        "where mstar_id = any(%s) and nav > 0",
        conn, params=(mstar_ids,),
    )
    df["nav_date"] = pd.to_datetime(df.nav_date)
    return {
        mid: g.sort_values("nav_date").drop_duplicates("nav_date", keep="last")
              .set_index("nav_date").nav
        for mid, g in df.groupby("mstar_id")
    }


def _bulk_indices(conn, codes: list[str]) -> dict[str, pd.Series]:
    df = pd.read_sql(
        "select index_code, date, close::float close from atlas_foundation.index_prices "
        "where index_code = any(%s) and close > 0",
        conn, params=(codes,),
    )
    df["date"] = pd.to_datetime(df.date)
    return {
        code: g.sort_values("date").drop_duplicates("date", keep="last").set_index("date").close
        for code, g in df.groupby("index_code")
    }


def _worst_windows(bench: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """The WORST_N deepest (peak->trough) drawdown windows off the bench NAV,
    each as (window_start, trough_date)."""
    scored = []
    for a, b in drawdown_windows(bench):
        seg = bench.loc[a:b]
        if len(seg) < 2:
            continue
        trough_date = seg.idxmin()
        depth = float(seg.min()) / float(bench.loc[a]) - 1.0
        scored.append((depth, a, trough_date))
    scored.sort(key=lambda t: t[0])  # most negative first
    return [(a, tr) for _, a, tr in scored[:WORST_N]]


def _roll_cagr(nl: NavLookup, first, last, asof, n_years: int) -> float | None:
    """Mean of the trailing N_ROLL_ANCHORS monthly rolling n_year CAGRs.

    An anchor t contributes only when BOTH legs sit inside the fund's real NAV
    coverage: t - n_years >= first (no fill before inception) and t <= last +
    FRESH (recent leg is real, not a stale forward-fill). None if no valid
    anchor -> the fund has no full n_year window reaching the as-of date.
    """
    vals = []
    for k in range(N_ROLL_ANCHORS):
        t = asof - MONTH * k
        t0 = t - pd.DateOffset(years=n_years)
        if t0 < first or t > last + FRESH:
            continue
        v1, v0 = nl.at(t), nl.at(t0)
        if not v1 or not v0 or v0 <= 0 or v1 <= 0:
            continue
        r = (v1 / v0) ** (1.0 / n_years) - 1.0
        if math.isfinite(r):
            vals.append(r)
    return sum(vals) / len(vals) if vals else None


def _full_period_cagr(s: pd.Series) -> float | None:
    if len(s) < 2:
        return None
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    g = float(s.iloc[-1]) / float(s.iloc[0])
    if yrs <= 0 or g <= 0:
        return None
    r = g ** (1.0 / yrs) - 1.0
    return r if math.isfinite(r) else None


def _best_year_stripped_cagr(s: pd.Series) -> float | None:
    """Full-period growth with the single best rolling-12m factor divided out,
    re-annualised over (life - 1y): the "one lucky year" test.

    Needs >=2y of history: with less than that the residual is annualised over
    <1y and the exponent amplifies noise (a 1.4y fund cannot meaningfully have
    "a year stripped"). The best 12m factor is searched DENSELY over every NAV
    date (a monthly grid undersamples and can miss the true peak window, which
    would make the stripped return spuriously exceed the full-period return).
    """
    if len(s) < 2:
        return None
    first, last = s.index[0], s.index[-1]
    yrs = (last - first).days / 365.25
    g_full = float(s.iloc[-1]) / float(s.iloc[0])
    if yrs < 2.0 or g_full <= 0:
        return None
    past = s.index - YEAR
    prior = s.asof(past).to_numpy()          # last NAV on/before each (date - 1y)
    factors = s.to_numpy() / prior
    factors = factors[(past >= first) & np.isfinite(factors) & (prior > 0)]
    if not len(factors):
        return None
    best = float(factors.max())
    g_strip = g_full / best
    ys = yrs - 1.0
    if best <= 0 or g_strip <= 0 or ys <= 0:
        return None
    r = g_strip ** (1.0 / ys) - 1.0
    return r if math.isfinite(r) else None


def _dn_capture(fund_nl: NavLookup, first, last, worst, bench_nl: NavLookup) -> float | None:
    """Sum of the fund's declines / sum of the market's declines across the
    WORST_N deepest drawdowns the fund lived through (fund existed at window
    start). Both legs off forward-filled NAV; skip windows before inception.
    None if the fund overlaps none of them or the market leg is non-negative.
    """
    num = den = 0.0
    used = 0
    for start, trough in worst:
        if start < first or trough > last + FRESH:
            continue
        bs, bt = bench_nl.at(start), bench_nl.at(trough)
        fs, ft = fund_nl.at(start), fund_nl.at(trough)
        if not (bs and bt and fs and ft) or bs <= 0 or fs <= 0:
            continue
        num += ft / fs - 1.0
        den += bt / bs - 1.0
        used += 1
    if used == 0 or den >= 0:
        return None
    r = num / den  # ratio of two declines -> positive fraction; _pct scales to %
    return r if math.isfinite(r) else None


def _beat_count(fund_nl, first, last, asof, idx_series):
    """Over up to N_BEAT_WINDOWS trailing monthly rolling-1y windows, count wins
    of fund 1y return over the benchmark index 1y return. Returns
    (beat_count, windows) or (None, None) if no window is evaluable."""
    idx_nl = NavLookup(idx_series)
    idx_first, idx_last = idx_series.index[0], idx_series.index[-1]
    beats = wins = 0
    for k in range(N_BEAT_WINDOWS):
        t = asof - MONTH * k
        t0 = t - YEAR
        if t0 < first or t > last + FRESH or t0 < idx_first or t > idx_last:
            continue
        fv1, fv0 = fund_nl.at(t), fund_nl.at(t0)
        iv1, iv0 = idx_nl.at(t), idx_nl.at(t0)
        if not (fv1 and fv0 and iv1 and iv0) or fv0 <= 0 or iv0 <= 0:
            continue
        wins += 1
        if (fv1 / fv0) > (iv1 / iv0):
            beats += 1
    return (beats, wins) if wins else (None, None)


def _benchmark_note(pb: str | None) -> tuple[str | None, str]:
    """(index_code or None, note) for a fund's primary_benchmark."""
    if not pb:
        return None, "no primary_benchmark on de_mf_master; benchmark legs NULL"
    hit = BENCHMARK_MAP.get(pb)
    if not hit:
        return None, f"no NSE index match for benchmark {pb!r}; benchmark legs NULL"
    code, kind = hit
    note = (f"approx: NSE price-return index {code!r}, not the fund's "
            f"total-return benchmark {pb!r}")
    if kind == "proxy":
        note += " (nearest-NSE proxy for a non-NSE benchmark)"
    return code, note


def compute_all(conn) -> list[dict]:
    funds = pd.read_sql(
        """select s.scheme_id, s.mstar_id, s.display_name, m.primary_benchmark
           from wealth.schemes s join wealth.holdings h using(scheme_id)
           left join atlas_foundation.de_mf_master m on m.mstar_id = s.mstar_id
           where s.asset_class = 'Equity'""",
        conn,
    ).drop_duplicates("scheme_id").sort_values("scheme_id")

    mstar_ids = [m for m in funds.mstar_id.dropna().unique().tolist()]
    nav_by = _bulk_navs(conn, mstar_ids)

    bench = nav_series(conn, BENCH_ID)
    bench_nl = NavLookup(bench)
    worst = _worst_windows(bench)

    # as-of = the book's latest NAV date (single calendar anchor for every fund)
    asof = max((s.index[-1] for s in nav_by.values() if len(s)), default=bench.index[-1])

    codes = sorted({_benchmark_note(pb)[0] for pb in funds.primary_benchmark.unique()} - {None})
    idx_by = _bulk_indices(conn, codes)

    rows = []
    for f in funds.itertuples():
        code, bnote = _benchmark_note(f.primary_benchmark)
        s = nav_by.get(f.mstar_id) if f.mstar_id else None

        if s is None or len(s) < 2:
            rows.append(dict(
                scheme_id=int(f.scheme_id), mstar_id=f.mstar_id,
                roll_3y_pct=None, roll_5y_pct=None, dn_capture_pct=None,
                best_year_stripped_pct=None, full_period_pct=None,
                beat_count=None, windows=None,
                benchmark_note=("no mstar_id: no NAV series" if not f.mstar_id
                                else "no usable NAV series"),
                verdict="insufficient_history",
            ))
            continue

        first, last = s.index[0], s.index[-1]
        nl = NavLookup(s)
        fresh = last >= asof - FRESH  # trailing 3y/5y must reach the current as-of

        # roll_3y/5y are CURRENT trailing numbers: only for funds still reporting.
        # full_period / best_year_stripped / dn_capture are historical -> always OK.
        roll3 = _roll_cagr(nl, first, last, asof, 3) if fresh else None
        roll5 = _roll_cagr(nl, first, last, asof, 5) if fresh else None
        dn = _dn_capture(nl, first, last, worst, bench_nl)
        best_strip = _best_year_stripped_cagr(s)
        full = _full_period_cagr(s)

        if code and code in idx_by:
            beat, nwin = _beat_count(nl, first, last, asof, idx_by[code])
        else:
            beat, nwin = None, None

        note = bnote
        if roll5 is not None:
            verdict = "scored"
        else:
            verdict = "insufficient_history"
            note += (f"; stale: last NAV {last.date()} (no current 5y return)"
                     if not fresh else "; <5y NAV history")

        rows.append(dict(
            scheme_id=int(f.scheme_id), mstar_id=f.mstar_id,
            roll_3y_pct=_pct(roll3), roll_5y_pct=_pct(roll5), dn_capture_pct=_pct(dn),
            best_year_stripped_pct=_pct(best_strip), full_period_pct=_pct(full),
            beat_count=beat, windows=nwin, benchmark_note=note, verdict=verdict,
        ))
    return rows


COLS = ("scheme_id", "mstar_id", "roll_3y_pct", "roll_5y_pct", "dn_capture_pct",
        "best_year_stripped_pct", "full_period_pct", "beat_count", "windows",
        "benchmark_note", "verdict")


def main() -> int:
    conn = connect()
    rows = compute_all(conn)

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.fund_performance")
    cur.execute(
        """create table wealth.fund_performance (
             scheme_id bigint primary key,
             mstar_id text,
             roll_3y_pct numeric(8,2), roll_5y_pct numeric(8,2),
             dn_capture_pct numeric(8,2), best_year_stripped_pct numeric(8,2),
             full_period_pct numeric(8,2), beat_count int, windows int,
             benchmark_note text, verdict text)"""
    )
    execute_values(
        cur,
        "insert into wealth.fund_performance (" + ",".join(COLS) + ") values %s",
        [tuple(r[c] for c in COLS) for r in rows],
        page_size=500,
    )
    cur.execute("revoke all on wealth.fund_performance from anon, authenticated")
    conn.commit()

    scored = [r for r in rows if r["verdict"] == "scored"]
    insuf = [r for r in rows if r["verdict"] == "insufficient_history"]
    with_bench = [r for r in rows if r["beat_count"] is not None]
    dn_vals = [r["dn_capture_pct"] for r in rows if r["dn_capture_pct"] is not None]
    print(f"fund_performance: {len(rows)} held equity funds "
          f"({len(scored)} scored, {len(insuf)} insufficient_history)")
    print(f"  benchmark legs computed on {len(with_bench)} funds "
          f"({len(rows) - len(with_bench)} funds have no mappable benchmark -> NULL legs)")
    if dn_vals:
        dn_vals.sort()
        print(f"  dn_capture on {len(dn_vals)} funds: "
              f"median {dn_vals[len(dn_vals)//2]:.0f}% "
              f"(protected <100%: {sum(1 for v in dn_vals if v < 100)})")
    if scored:
        r5 = sorted(r["roll_5y_pct"] for r in scored)
        print(f"  roll_5y median {r5[len(r5)//2]:.1f}% over {len(scored)} scored funds")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
