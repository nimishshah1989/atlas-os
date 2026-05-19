"""universe.get_investable — PIT Nifty 500 + ADV >= ₹5cr floor."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from atlas.trading.v6.universe import (
    InvestableFilter,
)


def _insert_universe_stock(session, iid: uuid.UUID, symbol: str, in_nifty_500: bool = True) -> None:
    """Insert a minimal atlas_universe_stocks row (all NOT NULL cols satisfied)."""
    session.execute(
        text("""
            INSERT INTO atlas.atlas_universe_stocks
                (instrument_id, symbol, company_name, tier, sector, in_nifty_500, effective_from)
            VALUES (:i, :sym, 'Test Co', 'Large', 'Financials', :n500, '2024-01-01')
            ON CONFLICT (instrument_id, effective_from) DO NOTHING
        """),
        {"i": str(iid), "sym": symbol, "n500": in_nifty_500},
    )


def _insert_ohlcv(session, iid: uuid.UUID, trade_date: date, close: float, volume: int) -> None:
    """Insert a single de_equity_ohlcv row."""
    session.execute(
        text("""
            INSERT INTO public.de_equity_ohlcv
                (instrument_id, date, close, volume, data_status)
            VALUES (:i, :d, :c, :v, 'validated')
            ON CONFLICT (instrument_id, date) DO NOTHING
        """),
        {"i": str(iid), "d": trade_date, "c": close, "v": volume},
    )


def test_filter_drops_below_adv_floor(tmp_db_session):
    """ADV < ₹5cr → excluded even if in Nifty 500.

    close=100, volume=100_000 → traded value = ₹1cr/day (below ₹5cr floor).
    """
    iid = uuid.uuid4()
    _insert_universe_stock(tmp_db_session, iid, "LOWVOL")
    # ₹1cr / day for 20 days
    for d in range(20):
        _insert_ohlcv(tmp_db_session, iid, date(2026, 1, d + 1), close=100.0, volume=100_000)

    f = InvestableFilter(adv_floor_cr=5.0)
    out = f.apply(tmp_db_session, ref_date=date(2026, 1, 20))
    assert iid not in {u.instrument_id for u in out}


def test_filter_keeps_above_adv_floor(tmp_db_session):
    """ADV >= ₹5cr → included when in Nifty 500.

    close=100, volume=1_000_000 → traded value = ₹10cr/day (above ₹5cr floor).
    """
    iid = uuid.uuid4()
    _insert_universe_stock(tmp_db_session, iid, "BIGVOL")
    # ₹10cr / day for 20 days
    for d in range(20):
        _insert_ohlcv(tmp_db_session, iid, date(2026, 1, d + 1), close=100.0, volume=1_000_000)

    f = InvestableFilter(adv_floor_cr=5.0)
    out = f.apply(tmp_db_session, ref_date=date(2026, 1, 20))
    assert iid in {u.instrument_id for u in out}
