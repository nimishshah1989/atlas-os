"""Point-in-time investable universe for the v6 trading model.

Universe = current Nifty 500 (via atlas_universe_stocks.in_nifty_500) AND
20d median traded value >= ₹5 crore.

Traded value = close * volume from public.de_equity_ohlcv (partitioned by year).
₹1 crore = ₹1e7.

When Plan 1A D1 backfill lands, swap the in_nifty_500 boolean to the PIT
atlas_index_membership table for survivorship-bias-free backtest.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger()


@dataclass(frozen=True)
class InvestableInstrument:
    instrument_id: uuid.UUID
    symbol: str
    sector: str | None
    median_adv_cr: float


@dataclass
class InvestableFilter:
    adv_floor_cr: float = 5.0
    adv_window_days: int = 20

    def apply(self, session: Session, ref_date: date) -> list[InvestableInstrument]:
        """Return all Nifty 500 stocks with 20d median ADV >= adv_floor_cr crore.

        Uses ~40 calendar days to capture 20 trading days.
        Traded value = close * volume; ₹1 crore = ₹1e7.
        """
        window_start = ref_date - timedelta(days=self.adv_window_days * 2)  # ~40 cal days
        rows = session.execute(
            text("""
                WITH adv AS (
                  SELECT
                    o.instrument_id,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (
                      ORDER BY o.close * o.volume
                    ) / 1e7 AS median_adv_cr
                    FROM public.de_equity_ohlcv o
                   WHERE o.date BETWEEN :s AND :e
                     AND o.close > 0
                     AND o.volume > 0
                   GROUP BY o.instrument_id
                )
                SELECT DISTINCT
                  u.instrument_id,
                  u.symbol,
                  u.sector,
                  adv.median_adv_cr
                  FROM atlas.atlas_universe_stocks u
                  JOIN adv USING (instrument_id)
                 WHERE u.in_nifty_500 = true
                   AND adv.median_adv_cr >= :floor
            """),
            {"s": window_start, "e": ref_date, "floor": self.adv_floor_cr},
        ).fetchall()

        log.info(
            "universe.apply",
            ref_date=str(ref_date),
            adv_floor_cr=self.adv_floor_cr,
            result_count=len(rows),
        )

        return [
            InvestableInstrument(
                instrument_id=uuid.UUID(str(r.instrument_id)),
                symbol=r.symbol,
                sector=r.sector,
                median_adv_cr=float(r.median_adv_cr or 0),
            )
            for r in rows
        ]


def get_investable(
    session: Session, ref_date: date, adv_floor_cr: float = 5.0
) -> list[InvestableInstrument]:
    """Convenience wrapper around InvestableFilter.apply."""
    return InvestableFilter(adv_floor_cr=adv_floor_cr).apply(session, ref_date)
