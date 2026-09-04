"""US-platform configuration: the market row plus the env accessors the providers use.

``MARKETS`` is imported at module level ON PURPOSE. If ``atlas.config`` has no US market
this module must fail at import time, loudly — never fall back to an inline default
(rule #0 / rule #4: nothing silent, nothing invented). Keys live in ``.env`` (loaded by
``atlas.config``) or the process environment; they are never read from any other file.
"""

from __future__ import annotations

import os

from atlas.config import MARKETS

CONFIG = MARKETS["us"]

PRICE_PROVIDERS = frozenset({"alpaca", "stooq_bulk"})
_DEFAULT_PRICE_PROVIDER = "alpaca"


def _require(name: str, hint: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} missing — {hint}")
    return value


def alpaca_keys() -> tuple[str, str]:
    """``(ALPACA_API_KEY, ALPACA_API_SECRET)`` — paper-trading keys from app.alpaca.markets."""
    key = _require("ALPACA_API_KEY", "set the Alpaca paper-account API key in .env")
    secret = _require("ALPACA_API_SECRET", "set the Alpaca paper-account API secret in .env")
    return key, secret


def edgar_identity() -> str:
    """SEC requires a ``"Name email"`` User-Agent on every EDGAR request."""
    return _require("EDGAR_IDENTITY", 'set it in .env as "Firstname Lastname email@domain"')


def fred_key() -> str:
    return _require(
        "FRED_API_KEY", "set the FRED API key in .env (same key India's ingest_macro uses)"
    )


def price_provider() -> str:
    """Which PriceProvider ``ingest_prices.py`` uses: ``alpaca`` (default) or ``stooq_bulk``."""
    value = os.environ.get("GLOBAL_PRICE_PROVIDER", _DEFAULT_PRICE_PROVIDER).strip().lower()
    if value not in PRICE_PROVIDERS:
        raise RuntimeError(
            f"GLOBAL_PRICE_PROVIDER={value!r} is not one of {sorted(PRICE_PROVIDERS)}"
        )
    return value
