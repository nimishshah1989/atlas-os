"""US-platform configuration: the market row plus the env accessors the providers use.

``MARKETS`` is imported at module level ON PURPOSE. If ``atlas.config`` has no US market
this module must fail at import time, loudly — never fall back to an inline default
(rule #0: nothing silent, nothing invented). Keys live in ``.env`` (loaded by
``atlas.config``) or the process environment; they are never read from any other file.
"""

from __future__ import annotations

import os

from atlas.config import MARKETS

CONFIG = MARKETS["us"]

PRICE_PROVIDERS = frozenset({"alpaca", "stooq_bulk"})


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
    """SEC fair-access: every EDGAR request carries a ``User-Agent`` naming a real contact
    (``"Firstname Lastname email@domain"``). The identity fetch refuses to run without it,
    and without an ``@`` in it — a name alone is not a contact."""
    value = _require("EDGAR_IDENTITY", 'set it in .env as "Firstname Lastname email@domain"')
    if "@" not in value:
        raise RuntimeError(
            'EDGAR_IDENTITY must name a contact address: "Firstname Lastname email@domain"'
        )
    return value


def fred_key() -> str | None:
    """``FRED_API_KEY`` if one is set, else ``None`` — which selects the KEYLESS transport.

    The ONLY accessor here that does not ``_require``. FRED publishes the same observations
    two ways: the JSON API (key, revision vintages, richer metadata) and the keyless CSV
    export behind its own "Download → CSV" button. Both are REAL prints from the same
    source, so a missing key is not a reason to refuse — it is a reason to take the other
    door, and ``providers/fred.fred_series`` dispatches on exactly this ``None``. Setting the
    key later moves every caller onto the JSON API with no code change.
    """
    return os.environ.get("FRED_API_KEY", "").strip() or None


def price_provider() -> str:
    """Which PriceProvider the nightly ``ingest_prices.py`` uses: ``alpaca`` or ``stooq_bulk``.

    No default on purpose: the SIP gate decides the spine, and a forgotten env var must not
    quietly ingest IEX-only bars under ``source='alpaca'``.
    """
    value = _require(
        "GLOBAL_PRICE_PROVIDER",
        f"set it in .env to one of {sorted(PRICE_PROVIDERS)} once the SIP gate has run",
    ).lower()
    if value not in PRICE_PROVIDERS:
        raise RuntimeError(
            f"GLOBAL_PRICE_PROVIDER={value!r} is not one of {sorted(PRICE_PROVIDERS)}"
        )
    return value
