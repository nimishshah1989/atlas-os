"""Cross-asset TSMOM crisis sleeve for v6 trading model.

Implements Moskowitz-Ooi-Pedersen (2012) time-series momentum on two ETF legs:
  - Gold proxy   : GOLDBEES (fallback: SETFGOLD)
  - G-Sec proxy  : GILT5YBEES (fallback: LIQUIDBEES when < 252d history)

Sleeve sizing per spec §7.6:
  sleeve_pct = 0.05 + 0.10 × (regime_score / 5)    → [0.05, 0.15]

TSMOM signal per asset:
  signal[a]          = sign(12m_ret[a]) × target_vol / realized_vol_63[a]
  positive_signal[a] = max(signal[a], 0)     # long-only sleeve in v0.1
  weight[a]          = positive_signal[a] / Σ positive_signal

If Σ positive_signal == 0 (both returns ≤ 0): sleeve goes to cash (legs=[]).

USDINR deferred to v0.2 (no PMS-friendly vehicle).

NOTE: fetch_etf_realized_vol_63d reads the pre-computed `realized_vol_63`
column from atlas_etf_metrics_daily rather than computing from raw prices.
This is consistent with the compute pipeline (atlas/compute/etfs.py) and
avoids a separate 63-day raw-price query. Deviation from spec docstring
is intentional and documented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

# Priority order: gold leg tries GOLDBEES first, SETFGOLD as fallback.
# G-Sec leg tries GILT5YBEES first (if >= 252d history), LIQUIDBEES as fallback.
_GOLD_PRIMARY = "GOLDBEES"
_GOLD_FALLBACK = "SETFGOLD"
_GSEC_PRIMARY = "GILT5YBEES"
_GSEC_FALLBACK = "LIQUIDBEES"

_MIN_HISTORY_DAYS = 252


@dataclass(frozen=True)
class SleeveLeg:
    ticker: str
    weight_in_sleeve: float  # 0..1, sleeve internal weight
    tsmom_signal: float  # positive value from sign(12m_ret) × target_vol/realized_vol


@dataclass(frozen=True)
class SleeveAllocation:
    ref_date: date
    sleeve_pct_of_book: float  # 5%-15% by regime score
    legs: list[SleeveLeg]  # 0-2 entries; empty if all 12m returns ≤ 0


def compute_sleeve_pct(regime_score: int) -> float:
    """Sleeve percentage of book from regime score.

    Formula: sleeve_pct = 0.05 + 0.10 × (regime_score / 5)
    Range: score=0 → 0.05 (5%), score=5 → 0.15 (15%).
    """
    return 0.05 + 0.10 * (regime_score / 5)


def fetch_etf_12m_return(session: Session, ticker: str, ref_date: date) -> float | None:
    """Fetch pre-computed 12-month return from atlas_etf_metrics_daily.

    Returns None if:
    - No row exists for (ticker, ref_date)
    - ret_12m column is NULL
    """
    row = session.execute(
        text(
            "SELECT ret_12m AS v FROM atlas.atlas_etf_metrics_daily WHERE ticker = :t AND date = :d"
        ),
        {"t": ticker, "d": ref_date},
    ).fetchone()
    if row is None or row.v is None:
        log.debug("etf_12m_return_missing", ticker=ticker, ref_date=str(ref_date))
        return None
    return float(row.v)


def fetch_etf_realized_vol_63d(session: Session, ticker: str, ref_date: date) -> float | None:
    """Fetch pre-computed 63-day realized annualized vol from atlas_etf_metrics_daily.

    Returns None if:
    - No row exists for (ticker, ref_date)
    - realized_vol_63 column is NULL
    - realized_vol_63 == 0 (guard for division-by-zero in TSMOM signal)

    NOTE: uses the pre-computed column (std of 63d daily returns × sqrt(252))
    computed by atlas/compute/etfs.py, consistent with the compute pipeline.
    """
    row = session.execute(
        text(
            "SELECT realized_vol_63 AS v"
            " FROM atlas.atlas_etf_metrics_daily"
            " WHERE ticker = :t AND date = :d"
        ),
        {"t": ticker, "d": ref_date},
    ).fetchone()
    if row is None or row.v is None:
        log.debug("etf_vol_missing", ticker=ticker, ref_date=str(ref_date))
        return None
    vol = float(row.v)
    if vol == 0.0:
        log.warning("etf_vol_zero", ticker=ticker, ref_date=str(ref_date))
        return None
    return vol


def _has_sufficient_history(session: Session, ticker: str, ref_date: date) -> bool:
    """Return True if ticker has at least _MIN_HISTORY_DAYS rows before ref_date.

    Used to decide GILT5YBEES vs LIQUIDBEES fallback (and GOLDBEES vs SETFGOLD).
    Counts rows in [ref_date - 365d, ref_date] as a proxy for 252 trading days.
    """
    cutoff = ref_date - timedelta(days=365)
    row = session.execute(
        text(
            "SELECT COUNT(*) AS v"
            " FROM atlas.atlas_etf_metrics_daily"
            " WHERE ticker = :t AND date >= :cutoff AND date <= :ref"
        ),
        {"t": ticker, "cutoff": cutoff, "ref": ref_date},
    ).fetchone()
    count = int(row.v) if row is not None and row.v is not None else 0
    return count >= _MIN_HISTORY_DAYS


def _compute_tsmom_signal(
    ret_12m: float | None,
    realized_vol: float | None,
    target_vol: float,
) -> float:
    """Compute TSMOM signal for one asset.

    signal = sign(ret_12m) × target_vol / realized_vol

    Returns 0.0 when:
    - ret_12m is None (missing data)
    - ret_12m == 0.0 (sign(0) = 0)
    - realized_vol is None (missing or zero vol)
    """
    if ret_12m is None or realized_vol is None:
        return 0.0
    sign_ret = math.copysign(1.0, ret_12m) if ret_12m != 0.0 else 0.0
    return sign_ret * (target_vol / realized_vol)


def _resolve_gold_ticker(session: Session, ref_date: date) -> str:
    """Return GOLDBEES if it has sufficient history, else SETFGOLD."""
    if _has_sufficient_history(session, _GOLD_PRIMARY, ref_date):
        return _GOLD_PRIMARY
    log.info(
        "gold_fallback",
        primary=_GOLD_PRIMARY,
        fallback=_GOLD_FALLBACK,
        ref_date=str(ref_date),
    )
    return _GOLD_FALLBACK


def _resolve_gsec_ticker(session: Session, ref_date: date) -> str:
    """Return GILT5YBEES if it has sufficient history, else LIQUIDBEES."""
    if _has_sufficient_history(session, _GSEC_PRIMARY, ref_date):
        return _GSEC_PRIMARY
    log.info(
        "gsec_fallback",
        primary=_GSEC_PRIMARY,
        fallback=_GSEC_FALLBACK,
        ref_date=str(ref_date),
    )
    return _GSEC_FALLBACK


def allocate(
    session: Session,
    ref_date: date,
    regime_score: int,
    target_asset_vol: float = 0.08,  # 8% annualized per asset
) -> SleeveAllocation:
    """Compute crisis sleeve allocation per spec §7.6.

    For each candidate asset (gold + G-Sec in priority order):
      signal = sign(12m_ret) × target_asset_vol / realized_vol_63
      positive_signal = max(signal, 0)     # long-only sleeve in v0.1
    Pick 1 asset per leg (gold leg + G-Sec leg).
    Normalize: sleeve_weight = positive_signal / Σ positive_signal.
    Wrap in SleeveAllocation.

    If Σ positive_signal == 0: returns SleeveAllocation with legs=[] (sleeve → cash).
    """
    sleeve_pct = compute_sleeve_pct(regime_score)

    # Resolve which ticker to use for each leg
    gold_ticker = _resolve_gold_ticker(session, ref_date)
    gsec_ticker = _resolve_gsec_ticker(session, ref_date)

    # Fetch inputs for each leg
    gold_ret = fetch_etf_12m_return(session, gold_ticker, ref_date)
    gold_vol = fetch_etf_realized_vol_63d(session, gold_ticker, ref_date)
    gsec_ret = fetch_etf_12m_return(session, gsec_ticker, ref_date)
    gsec_vol = fetch_etf_realized_vol_63d(session, gsec_ticker, ref_date)

    log.debug(
        "crisis_sleeve_inputs",
        ref_date=str(ref_date),
        gold_ticker=gold_ticker,
        gold_ret=gold_ret,
        gold_vol=gold_vol,
        gsec_ticker=gsec_ticker,
        gsec_ret=gsec_ret,
        gsec_vol=gsec_vol,
    )

    # Compute TSMOM signals (0.0 when data missing or return ≤ 0)
    gold_signal = _compute_tsmom_signal(gold_ret, gold_vol, target_asset_vol)
    gsec_signal = _compute_tsmom_signal(gsec_ret, gsec_vol, target_asset_vol)

    # Long-only: clamp negatives to 0
    gold_positive = max(gold_signal, 0.0)
    gsec_positive = max(gsec_signal, 0.0)

    total_positive = gold_positive + gsec_positive

    if total_positive == 0.0:
        log.info(
            "crisis_sleeve_all_zero",
            ref_date=str(ref_date),
            gold_signal=gold_signal,
            gsec_signal=gsec_signal,
        )
        return SleeveAllocation(
            ref_date=ref_date,
            sleeve_pct_of_book=sleeve_pct,
            legs=[],
        )

    # Normalize weights
    legs: list[SleeveLeg] = []
    if gold_positive > 0.0:
        legs.append(
            SleeveLeg(
                ticker=gold_ticker,
                weight_in_sleeve=gold_positive / total_positive,
                tsmom_signal=gold_positive,
            )
        )
    if gsec_positive > 0.0:
        legs.append(
            SleeveLeg(
                ticker=gsec_ticker,
                weight_in_sleeve=gsec_positive / total_positive,
                tsmom_signal=gsec_positive,
            )
        )

    log.info(
        "crisis_sleeve_allocated",
        ref_date=str(ref_date),
        regime_score=regime_score,
        sleeve_pct=sleeve_pct,
        legs=[{"ticker": leg.ticker, "weight": leg.weight_in_sleeve} for leg in legs],
    )

    return SleeveAllocation(
        ref_date=ref_date,
        sleeve_pct_of_book=sleeve_pct,
        legs=legs,
    )
