"""Indian Fama-French factor returns: MKT, SMB, WML.

Computes daily factor returns and upserts to atlas_factor_returns_daily.

Data sources:
  MKT: public.de_index_prices (Nifty 500) - atlas_macro_daily (T-bill)
  SMB: atlas_stock_metrics_daily (ret_1d) + atlas_universe_stocks (tier)
       Schema deviation: atlas_universe_stocks has NO market_cap/shares_outstanding.
       Tier (Large/Mid/Small/Micro) used as size proxy. Documented here.
  WML: atlas_stock_metrics_daily (ret_1d, ret_12m_1m)

Size proxy mapping (no market_cap column in atlas_universe_stocks v087):
  "Small" cap (quintile-1) = tier IN ('Small', 'Micro')
  "Large" cap (quintile-5) = tier IN ('Large')
  Mid tier excluded from SMB spread (neither extreme).
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

_FALLBACK_TBILL_ANNUAL = 0.06  # 6% fallback when atlas_macro_daily is NULL
_SMALL_TIERS = ("Small", "Micro")
_LARGE_TIERS = ("Large",)
_WML_DECILE_N = 25  # top/bottom 25 stocks (approx top/bottom decile of ~250 active)
_WML_MIN_UNIVERSE = 10  # minimum stocks to compute WML


# ---------------------------------------------------------------------------
# Pure helpers (no DB; fully testable)
# ---------------------------------------------------------------------------


def _daily_tbill_rate(annual_rate: Decimal | None) -> float:
    """Convert annualized T-bill to daily (ACT/252). NULL → 0.0."""
    if annual_rate is None:
        return 0.0
    return float(annual_rate) / 252.0


def _mkt_excess_from_values(nifty_ret: float | None, daily_tbill: float) -> float | None:
    """mkt_excess = nifty_daily_ret - daily_tbill. None if nifty_ret is None."""
    if nifty_ret is None:
        return None
    return nifty_ret - daily_tbill


def _smb_from_tiers(
    small_returns: list[float],
    large_returns: list[float],
) -> float | None:
    """SMB = mean(small-tier ret) - mean(large-tier ret).

    Returns None if either tier has zero observations.
    """
    if not small_returns or not large_returns:
        return None
    small_mean = sum(small_returns) / len(small_returns)
    large_mean = sum(large_returns) / len(large_returns)
    return small_mean - large_mean


def _wml_from_mom_series(
    mom_series: list[float],
    ret_series: list[float],
    decile_n: int = _WML_DECILE_N,
) -> float | None:
    """WML = mean_ret(top decile by 12-1 momentum) - mean_ret(bottom decile).

    Args:
        mom_series: 12-1 momentum values (ret_12m_1m) for each stock.
        ret_series: same-day ret_1d for each stock (the return that accrues).
        decile_n:   number of stocks in each decile bucket.

    Returns None if too few valid stocks (< 2 × decile_n or < _WML_MIN_UNIVERSE).
    """
    # Filter NaN pairs
    pairs = [
        (m, r)
        for m, r in zip(mom_series, ret_series, strict=False)
        if m is not None and not math.isnan(m) and r is not None and not math.isnan(r)
    ]
    n = len(pairs)
    if n < max(_WML_MIN_UNIVERSE, 2 * decile_n):
        return None

    pairs_sorted = sorted(pairs, key=lambda p: p[0])
    bottom_rets = [p[1] for p in pairs_sorted[:decile_n]]
    top_rets = [p[1] for p in pairs_sorted[-decile_n:]]

    winner_mean = sum(top_rets) / len(top_rets)
    loser_mean = sum(bottom_rets) / len(bottom_rets)
    return winner_mean - loser_mean


# ---------------------------------------------------------------------------
# DB queries
# ---------------------------------------------------------------------------


def _fetch_nifty500_daily_ret(session: Session, ref_date: date) -> float | None:
    """Compute Nifty 500 daily return from public.de_index_prices."""
    row = session.execute(
        text("""
            SELECT
                curr.close AS today_close,
                prev.close AS prev_close
            FROM public.de_index_prices curr
            JOIN public.de_index_prices prev
              ON prev.index_code = curr.index_code
             AND prev.date = (
                 SELECT MAX(p2.date)
                 FROM public.de_index_prices p2
                 WHERE p2.index_code = 'NIFTY 500'
                   AND p2.date < :ref_date
                   AND p2.close IS NOT NULL
             )
            WHERE curr.index_code = 'NIFTY 500'
              AND curr.date = :ref_date
              AND curr.close IS NOT NULL
        """),
        {"ref_date": ref_date},
    ).fetchone()

    if row is None or row.prev_close is None or float(row.prev_close) == 0.0:
        return None
    return (float(row.today_close) - float(row.prev_close)) / float(row.prev_close)


def _fetch_tbill(session: Session, ref_date: date) -> Decimal | None:
    """Read risk_free_91d from atlas_macro_daily for ref_date."""
    row = session.execute(
        text("""
            SELECT risk_free_91d
            FROM atlas.atlas_macro_daily
            WHERE date = :ref_date
        """),
        {"ref_date": ref_date},
    ).fetchone()
    if row is None or row.risk_free_91d is None:
        return None
    return row.risk_free_91d


def _fetch_smb_inputs(session: Session, ref_date: date) -> tuple[list[float], list[float]]:
    """Fetch ret_1d split by tier for SMB computation.

    Returns (small_returns, large_returns) where small = Small/Micro tier,
    large = Large tier. Mid tier excluded from the spread.
    """
    rows = session.execute(
        text("""
            SELECT u.tier, m.ret_1d
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_universe_stocks u USING (instrument_id)
            WHERE m.date = :ref_date
              AND m.ret_1d IS NOT NULL
              AND u.effective_to IS NULL
              AND u.tier IS NOT NULL
        """),
        {"ref_date": ref_date},
    ).fetchall()

    small_returns = [float(r.ret_1d) for r in rows if r.tier in _SMALL_TIERS]
    large_returns = [float(r.ret_1d) for r in rows if r.tier in _LARGE_TIERS]
    return small_returns, large_returns


def _fetch_wml_inputs(session: Session, ref_date: date) -> tuple[list[float], list[float]]:
    """Fetch (ret_12m_1m, ret_1d) pairs for WML computation.

    12-1 momentum (ret_12m_1m) is used to rank; ret_1d is the return that accrues.
    """
    rows = session.execute(
        text("""
            SELECT ret_12m_1m, ret_1d
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_universe_stocks u USING (instrument_id)
            WHERE m.date = :ref_date
              AND m.ret_12m_1m IS NOT NULL
              AND m.ret_1d IS NOT NULL
              AND u.effective_to IS NULL
        """),
        {"ref_date": ref_date},
    ).fetchall()

    mom_series = [float(r.ret_12m_1m) for r in rows]
    ret_series = [float(r.ret_1d) for r in rows]
    return mom_series, ret_series


# ---------------------------------------------------------------------------
# Public compute functions (per spec §5.3 Step 1 API)
# ---------------------------------------------------------------------------


def compute_mkt_excess(session: Session, ref_date: date) -> float | None:
    """Nifty 500 daily return − 91d T-bill rate (daily).

    T-bill fallback: 0.06/252 when atlas_macro_daily.risk_free_91d is NULL.
    Returns None when Nifty 500 close is missing for ref_date.
    """
    nifty_ret = _fetch_nifty500_daily_ret(session, ref_date)
    if nifty_ret is None:
        log.debug("factor_returns.mkt_excess.missing_nifty", date=str(ref_date))
        return None

    tbill_annual = _fetch_tbill(session, ref_date)
    if tbill_annual is None:
        log.debug(
            "factor_returns.tbill_fallback",
            date=str(ref_date),
            fallback=_FALLBACK_TBILL_ANNUAL,
        )
    daily_rf = _daily_tbill_rate(tbill_annual)
    return _mkt_excess_from_values(nifty_ret, daily_rf)


def compute_smb(session: Session, ref_date: date) -> float | None:
    """Small-minus-Big factor return on ref_date.

    Schema deviation: no market_cap column; using tier as size proxy.
    Small = tier IN ('Small','Micro'), Large = tier IN ('Large').
    Returns None when either tier has zero active stocks with ret_1d.
    """
    small_returns, large_returns = _fetch_smb_inputs(session, ref_date)

    if not small_returns:
        log.debug("factor_returns.smb.no_small_tier", date=str(ref_date))
    if not large_returns:
        log.debug("factor_returns.smb.no_large_tier", date=str(ref_date))

    result = _smb_from_tiers(small_returns, large_returns)
    log.debug(
        "factor_returns.smb",
        date=str(ref_date),
        n_small=len(small_returns),
        n_large=len(large_returns),
        smb=result,
    )
    return result


def compute_wml(session: Session, ref_date: date) -> float | None:
    """Winners-minus-Losers factor return on ref_date.

    Top/bottom 25 stocks by 12-1 momentum. Returns None when universe too small.
    """
    mom_series, ret_series = _fetch_wml_inputs(session, ref_date)
    result = _wml_from_mom_series(mom_series, ret_series)
    log.debug(
        "factor_returns.wml",
        date=str(ref_date),
        n_universe=len(mom_series),
        wml=result,
    )
    return result


# ---------------------------------------------------------------------------
# Upsert + range compute
# ---------------------------------------------------------------------------


def _upsert_row(
    session: Session,
    ref_date: date,
    mkt_excess: float | None,
    smb: float | None,
    wml: float | None,
) -> None:
    """INSERT ... ON CONFLICT DO UPDATE for one date row."""
    session.execute(
        text("""
            INSERT INTO atlas.atlas_factor_returns_daily
                (date, mkt_excess, smb, wml)
            VALUES (:date, :mkt, :smb, :wml)
            ON CONFLICT (date) DO UPDATE SET
                mkt_excess = EXCLUDED.mkt_excess,
                smb        = EXCLUDED.smb,
                wml        = EXCLUDED.wml
        """),
        {
            "date": ref_date,
            "mkt": mkt_excess,
            "smb": smb,
            "wml": wml,
        },
    )


def _trading_days_in_range(session: Session, start: date, end: date) -> list[date]:
    """Return dates in range that have at least one stock metric row.

    Uses atlas_stock_metrics_daily as the trading-day oracle.
    Falls back to calendar days when no metrics rows exist yet.
    """
    rows = session.execute(
        text("""
            SELECT DISTINCT date
            FROM atlas.atlas_stock_metrics_daily
            WHERE date BETWEEN :start AND :end
            ORDER BY date
        """),
        {"start": start, "end": end},
    ).fetchall()

    if rows:
        return [r.date for r in rows]

    # Fallback: use index prices as trading-day oracle
    rows = session.execute(
        text("""
            SELECT DISTINCT date
            FROM public.de_index_prices
            WHERE index_code = 'NIFTY 500'
              AND date BETWEEN :start AND :end
            ORDER BY date
        """),
        {"start": start, "end": end},
    ).fetchall()
    return [r.date for r in rows]


def compute_and_upsert_for_range(
    session: Session,
    start: date,
    end: date,
    commit_every: int = 20,
) -> dict[str, int]:
    """Compute MKT/SMB/WML for every trading day in [start, end] and upsert.

    Args:
        session: SQLAlchemy session (must support commit).
        start: First date (inclusive).
        end: Last date (inclusive).
        commit_every: Batch commit every N rows.

    Returns dict with row counts: {written, skipped, total_days}.
    """
    trading_days = _trading_days_in_range(session, start, end)
    log.info(
        "factor_returns.range_start",
        start=str(start),
        end=str(end),
        total_trading_days=len(trading_days),
    )

    written = 0
    skipped = 0

    for _i, ref_date in enumerate(trading_days):
        mkt = compute_mkt_excess(session, ref_date)
        smb = compute_smb(session, ref_date)
        wml = compute_wml(session, ref_date)

        if mkt is None and smb is None and wml is None:
            log.debug("factor_returns.all_null_skip", date=str(ref_date))
            skipped += 1
            continue

        _upsert_row(session, ref_date, mkt, smb, wml)
        written += 1

        if written % commit_every == 0:
            session.commit()
            log.info(
                "factor_returns.progress",
                written=written,
                skipped=skipped,
                total=len(trading_days),
            )

    session.commit()
    log.info(
        "factor_returns.range_done",
        written=written,
        skipped=skipped,
        total_days=len(trading_days),
    )
    return {"written": written, "skipped": skipped, "total_days": len(trading_days)}
