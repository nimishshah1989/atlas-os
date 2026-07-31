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

# CPP txn_type values that move shares. CORPUS_IN is capital, BONUS is a corporate
# action — neither is a trade, and counting them as one would corrupt realized P&L.
_TRADE_TYPES = {"BUY": "buy", "SELL": "sell"}

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
) -> dict[str, Any] | None:
    """One CPP transaction as a portfolio_trades row. None when it is not a trade."""
    side = _TRADE_TYPES.get((txn.get("txn_type") or "").strip().upper())
    if side is None:
        return None
    return {
        "trade_date": txn["txn_date"],
        "asset_class": asset_class,
        "instrument_key": instrument_key,
        "symbol": instrument_key.split(":", 1)[1],
        "side": side,
        "qty": txn["quantity"],
        "price": txn["price"],
        "value": txn["amount"],
        "cost": txn["cost_rate"],
        "reason": "manual",
        "source_txn_id": txn["id"],
    }
