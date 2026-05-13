"""Intraday RS vs Nifty50 (return since open)."""

from __future__ import annotations

from decimal import Decimal

# NSE:NIFTY 50 KiteConnect instrument token
NIFTY50_TOKEN: int = 256265

# Kite instrument token → display symbol for all tracked NSE indices.
# Values must exactly match the `symbol` column in atlas_nifty_intraday.
INDEX_TOKENS: dict[int, str] = {
    256265: "NIFTY 50",
    260105: "NIFTY BANK",
    288009: "NIFTY MID100",
    289281: "NIFTY SMLCAP",
    259849: "NIFTY IT",
}


def compute_rs(
    stock_return: Decimal | None,
    nifty_return: Decimal | None,
) -> Decimal | None:
    """Compute intraday Relative Strength of a stock vs Nifty50.

    RS = stock_return / nifty_return

    Returns None (not 0, not Inf) on zero denominator or missing inputs,
    per financial domain rules: NULL in financial calc must produce NULL.

    Args:
        stock_return: Stock's return since open (Decimal or None).
        nifty_return: Nifty50's return since open (Decimal or None).

    Returns:
        Decimal RS ratio or None if inputs are None / Nifty return is zero.
    """
    if stock_return is None or nifty_return is None:
        return None
    if nifty_return == Decimal(0):
        return None
    return stock_return / nifty_return


def compute_return_since_open(
    current_price: Decimal | None,
    open_price: Decimal | None,
) -> Decimal | None:
    """Compute return from open to current price.

    return_since_open = (current_price - open_price) / open_price

    Returns None on zero open_price or missing inputs.

    Args:
        current_price: Current (or close) price as Decimal or None.
        open_price: Opening price of the session as Decimal or None.

    Returns:
        Decimal return (e.g. 0.0123 for +1.23%) or None.
    """
    if current_price is None or open_price is None:
        return None
    if open_price == Decimal(0):
        return None
    return (current_price - open_price) / open_price
