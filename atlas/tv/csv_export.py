# atlas/tv/csv_export.py
"""Export Atlas paper portfolio as TradingView-compatible CSV.

Format:
  Symbol,Side,Qty,Fill Price,Commission,Closing Time
  NSE:RELIANCE,Buy,10,2800.00,,2024-09-17 0:00:00
  NSE:RELIANCE,Sell,10,3000.00,,2024-09-18 0:00:00
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.db import get_engine

log = structlog.get_logger(__name__)

_COLUMNS = ["Symbol", "Side", "Qty", "Fill Price", "Commission", "Closing Time"]


def _fmt_date(d: object) -> str:
    if d is None:
        return ""
    return f"{d} 0:00:00"


def _fmt_price(p: object) -> str:
    if p is None:
        return ""
    return f"{Decimal(str(p)):.2f}"


def export_portfolio_csv(portfolio_id: str, engine: Engine | None = None) -> bytes:
    """Return TV-format CSV bytes for all lots in a paper portfolio."""
    engine = engine or get_engine()
    sql = text("""
        SELECT
            au.symbol,
            p.quantity,
            p.entry_price,
            p.entry_date::text AS entry_date,
            p.exit_price,
            p.exit_date::text AS exit_date
        FROM atlas.atlas_paper_portfolio p
        JOIN atlas.atlas_universe_stocks au ON au.instrument_id = p.instrument_id
        WHERE p.portfolio_id = :pid
        ORDER BY p.entry_date, au.symbol
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"pid": portfolio_id}).mappings().all()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_COLUMNS, lineterminator="\n")
    writer.writeheader()

    for row in rows:
        symbol = f"NSE:{row['symbol']}"
        qty = str(row["quantity"])
        writer.writerow(
            {
                "Symbol": symbol,
                "Side": "Buy",
                "Qty": qty,
                "Fill Price": _fmt_price(row["entry_price"]),
                "Commission": "",
                "Closing Time": _fmt_date(row["entry_date"]),
            }
        )
        if row["exit_date"] is not None:
            writer.writerow(
                {
                    "Symbol": symbol,
                    "Side": "Sell",
                    "Qty": qty,
                    "Fill Price": _fmt_price(row["exit_price"]),
                    "Commission": "",
                    "Closing Time": _fmt_date(row["exit_date"]),
                }
            )

    log.info("tv_csv_export.done", portfolio_id=portfolio_id, lots=len(rows))
    return buf.getvalue().encode("utf-8")
