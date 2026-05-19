"""5-signal macro regime composite for v6 trading model.

Reads atlas_market_regime_daily to compute a regime score (0-5 bearish
signals) and maps it to a gross portfolio multiplier.

Signals (per chunk spec §7.2 task spec — not spec §7.2 which has FII/DXY):
  1. nifty500_above_ema_200 = false          → bearish
  2. pct_above_ema_200 < 0.30                → bearish
  3. india_vix > 22                          → bearish
  4. ad_ratio < 0.40                         → bearish
  5. dislocation_active = true               → bearish

All signals are fail-open: NULL field → signal is silent (not bearish).

Hysteresis is deferred to v0.1 refinement (per chunk spec: "skip hysteresis
for v0.1"). Score is computed directly from the ref_date snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()

# Gross multiplier table per spec §7.2
_SCORE_TO_MULTIPLIER: dict[int, float] = {
    0: 1.10,
    1: 1.00,
    2: 0.80,
    3: 0.55,
    4: 0.35,
    5: 0.20,
}

_SCORE_TO_LEVEL: dict[int, str] = {
    0: "calm",
    1: "normal",
    2: "yellow",
    3: "orange",
    4: "red",
    5: "crash",
}

# Bearish thresholds (fail-open: None → not bearish)
_BREADTH_BEARISH_THRESHOLD = 0.30
_VIX_BEARISH_THRESHOLD = 22.0
_AD_RATIO_BEARISH_THRESHOLD = 0.40


@dataclass(frozen=True)
class RegimeState:
    date: date
    score: int  # 0..5
    level: str  # 'calm'|'normal'|'yellow'|'orange'|'red'|'crash'
    gross_multiplier: float
    signals: list[dict] = field(default_factory=list)


def compute_regime(session: Session, ref_date: date) -> RegimeState:
    """Compute the 5-signal macro regime composite for ref_date.

    Reads one row from atlas_market_regime_daily. Raises ValueError if no
    row exists for ref_date (regime is required; cannot silently proceed).

    Each signal is fail-open: NULL reading → not bearish.
    Returns RegimeState with score, level, gross_multiplier, and per-signal detail.
    """
    row = session.execute(
        text("""
            SELECT
                nifty500_above_ema_200,
                pct_above_ema_200,
                india_vix,
                ad_ratio,
                dislocation_active
              FROM atlas.atlas_market_regime_daily
             WHERE date = :d
             LIMIT 1
        """),
        {"d": ref_date},
    ).fetchone()

    if row is None:
        raise ValueError(
            f"No atlas_market_regime_daily row for {ref_date}. "
            "Cannot compute regime without market breadth data."
        )

    signals: list[dict] = []
    bearish_count = 0

    # Signal 1: Nifty 500 trend
    nifty_above = row.nifty500_above_ema_200
    nifty_firing = False if (nifty_above is None) else (not bool(nifty_above))
    if nifty_firing:
        bearish_count += 1
    signals.append(
        {
            "name": "nifty500_trend",
            "firing": nifty_firing,
            "reading": None if nifty_above is None else bool(nifty_above),
        }
    )

    # Signal 2: Breadth
    pct_above = row.pct_above_ema_200
    breadth_firing = (
        False if (pct_above is None) else (float(pct_above) < _BREADTH_BEARISH_THRESHOLD)
    )
    if breadth_firing:
        bearish_count += 1
    signals.append(
        {
            "name": "breadth",
            "firing": breadth_firing,
            "reading": None if pct_above is None else float(pct_above),
        }
    )

    # Signal 3: VIX
    vix = row.india_vix
    vix_firing = False if (vix is None) else (float(vix) > _VIX_BEARISH_THRESHOLD)
    if vix_firing:
        bearish_count += 1
    signals.append(
        {
            "name": "india_vix",
            "firing": vix_firing,
            "reading": None if vix is None else float(vix),
        }
    )

    # Signal 4: A/D ratio
    ad = row.ad_ratio
    ad_firing = False if (ad is None) else (float(ad) < _AD_RATIO_BEARISH_THRESHOLD)
    if ad_firing:
        bearish_count += 1
    signals.append(
        {
            "name": "ad_ratio",
            "firing": ad_firing,
            "reading": None if ad is None else float(ad),
        }
    )

    # Signal 5: Dislocation
    dislocation = row.dislocation_active
    dislocation_firing = False if (dislocation is None) else bool(dislocation)
    if dislocation_firing:
        bearish_count += 1
    signals.append(
        {
            "name": "dislocation",
            "firing": dislocation_firing,
            "reading": None if dislocation is None else bool(dislocation),
        }
    )

    score = bearish_count
    level = _SCORE_TO_LEVEL[score]
    gross_multiplier = _SCORE_TO_MULTIPLIER[score]

    log.info(
        "regime.computed",
        ref_date=str(ref_date),
        score=score,
        level=level,
        gross_multiplier=gross_multiplier,
        signals_firing=[s["name"] for s in signals if s["firing"]],
    )

    return RegimeState(
        date=ref_date,
        score=score,
        level=level,
        gross_multiplier=gross_multiplier,
        signals=signals,
    )
