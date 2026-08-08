"""Map CPP rows onto Atlas shapes. Pure — no I/O, no DB handles.

Two things here are load-bearing and non-obvious:

1. Cash is whatever CPP tags ``asset_class = 'CASH'``. That already covers every
   liquid ETF (LIQUIDBEES, LIQUIDCASE, LIQUIDETF) — verified 2026-07-31 across all
   3,340 live rows, zero LIQUID-named rows misfiled as EQUITY. So there is no symbol
   list here to go stale. GOLDBEES and SILVERBEES stay positions: asset-class
   exposure, not cash.

2. A SELL's price is ``price`` (net rate, matching the backoffice FIFO), never
   ``cost_rate`` (all-in incl. taxes). Using the all-in rate would overstate every
   realized gain by the transaction costs.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# The three UCCs, locked by the FM 2026-07-31.
CODE_BY_CLIENT_CODE: dict[str, str] = {
    "BJ53": "leaders",
    "BJ53IND": "ind11",
    "JR100PASS": "passive",
}

# CPP txn_type -> portfolio_trades.side.
#
# CORPUS_IN is a securities transfer-IN, not cash (verified 2026-07-31: all 17 rows
# across the three books carry a real quantity and price). It opens a position, so it
# belongs in the trade log — otherwise RELIANCE appears SOLD in Oct-2020 with no record
# of ever arriving. portfolio_trades.reason already has 'inception' for exactly this.
#
# BONUS is a buy that cost nothing. It used to be absent here, because bonus shares
# arrive at price 0 and portfolio_trades' CHECK (price > 0) physically refused them —
# so the two real BJ53 rows (AARTIDRUGS 84, CDSL 136) were dropped and Atlas's trade
# log could not account for 220 shares CPP holds. maal_cpp_ddl.sql relaxes that CHECK
# for reason='bonus' only, so they are now recorded as what they are.
_TRADE_TYPES = {"BUY": "buy", "SELL": "sell", "CORPUS_IN": "buy", "BONUS": "buy"}

# The reason a trade carries, when it is not ordinary desk activity.
#   CORPUS_IN -> 'inception': a securities transfer-in, not a decision. BJ53's whole
#     opening book arrived this way; without it those names read as sold with no
#     record of ever arriving.
#   BONUS -> 'bonus': the string the relaxed price CHECK keys on. The engine never
#     writes it, so a zero-price engine trade is still rejected.
_REASON_BY_TYPE = {"CORPUS_IN": "inception", "BONUS": "bonus"}

_QUANT = Decimal("0.0001")


def is_cash(asset_class: str | None) -> bool:
    """True when CPP has classified the instrument as cash (incl. liquid ETFs)."""
    return (asset_class or "").strip().upper() == "CASH"


def split_cash_and_positions(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition holdings into (positions, cash_rows) on CPP's asset_class."""
    positions = [r for r in rows if not is_cash(r.get("asset_class"))]
    cash_rows = [r for r in rows if is_cash(r.get("asset_class"))]
    return positions, cash_rows


def weight_pct(position_value: Decimal, total_value: Decimal) -> Decimal:
    """Weight as a percent of TOTAL portfolio value, cash included.

    CPP's own weight_pct divides by invested value only, so its weights always sum
    to 100 and cash reads 0%. Atlas needs cash to be visible, so it recomputes.
    """
    if not total_value or total_value <= 0:
        return Decimal("0")
    return (position_value / total_value * 100).quantize(_QUANT)


def trade_from_txn(
    txn: dict[str, Any],
    instrument_key: str,
    asset_class: str,
    symbol: str,
) -> dict[str, Any] | None:
    """One CPP transaction as a portfolio_trades row. None when it is not a trade.

    ``instrument_key`` MUST be the instrument_master UUID, not a "stock:SYMBOL"
    string. That is the engine's existing convention for this column, and the
    portfolio detail page casts it with ``::uuid[]`` — a readable key makes that
    query throw, and the page 404s instead of failing loudly. ``symbol`` is
    therefore passed in rather than parsed back out of the key.
    """
    kind = (txn.get("txn_type") or "").strip().upper()
    side = _TRADE_TYPES.get(kind)
    if side is None:
        return None
    return {
        "trade_date": txn["txn_date"],
        "asset_class": asset_class,
        "instrument_key": instrument_key,
        "symbol": symbol,
        "side": side,
        "qty": txn["quantity"],
        "price": txn["price"],
        "value": txn["amount"],
        "cost": txn["cost_rate"],
        "reason": _REASON_BY_TYPE.get(kind, "manual"),
        "source_txn_id": txn["id"],
    }
