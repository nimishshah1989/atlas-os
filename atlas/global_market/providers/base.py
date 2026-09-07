"""Provider Protocols — the DataFrame shapes the pipeline scripts consume.

Adapters (``alpaca``, ``stooq_bulk``, ``fred``) do the I/O and are the ONLY off-box boundary
of the US platform. The nightly price spine is selected by ``GLOBAL_PRICE_PROVIDER``
(``config.price_provider()``). A holdings Protocol arrives with its first adapter (Phase 2).

Every adapter keeps ``calls: Counter[str]`` — requests per endpoint, a failed request
included (it spent budget). The free tiers are a monitored metric, so the pipeline script
turns that counter into ``atlas_global.provider_calls`` rows; the write happens in the
script, never here (adapters stay I/O-in, DataFrame-out).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal, Protocol

import pandas as pd

Adjustment = Literal["raw", "split", "all"]

# Column contracts. Prices are as delivered by the provider (raw, split- or all-adjusted
# per the request), as ``Decimal`` (USD is money); ``date`` is the exchange-local (New York)
# calendar date of the bar.
BAR_COLUMNS: tuple[str, ...] = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
)
ASSET_COLUMNS: tuple[str, ...] = (
    "symbol",
    "name",
    "exchange",
    "asset_class",
    "tradable",
    "fractionable",
    "provider_id",
)
# One row per corporate action, keyed by (symbol, ex_date, action_type). The two value
# columns are mutually exclusive by action type and NEVER by field name: a share-ratio event
# (any split, a stock dividend) fills `ratio` = new shares per old share, and a cash event
# fills `cash_amount` in USD per share. Providers name both "rate" — Alpaca's CashDividend
# and StockDividend both carry `.rate`, meaning dollars in one and shares in the other — so
# an adapter that keys on the field rather than the type records stock dividends as cash.
ACTION_COLUMNS: tuple[str, ...] = (
    "symbol",
    "ex_date",
    "action_type",
    "ratio",
    "cash_amount",
)


class PriceProvider(Protocol):
    """Daily bars for many symbols over a date range."""

    name: str

    def bars(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        adjustment: str,
    ) -> pd.DataFrame:
        """One row per (symbol, session) with :data:`BAR_COLUMNS`; empty frame when none.

        ``adjustment`` is an :data:`Adjustment` for a feed that can promise one; an adapter
        whose source does not say what its prices carry accepts only its own sentinel
        (``stooq_bulk``: ``"unknown"``) and refuses the rest.
        """
        ...


class AssetProvider(Protocol):
    """The provider's tradable universe (identity flags, not prices)."""

    name: str

    def assets(self) -> pd.DataFrame:
        """One row per asset with :data:`ASSET_COLUMNS`."""
        ...


class ActionProvider(Protocol):
    """Splits and dividends by ex-date — the events that re-base an adjusted price series."""

    name: str

    def actions(self, symbols: Sequence[str], start: date, end: date) -> pd.DataFrame:
        """One row per (symbol, ex_date, action_type) with :data:`ACTION_COLUMNS`; empty
        frame when none. An event type the adapter cannot read UNAMBIGUOUSLY is omitted and
        reported, never mapped on a guess — a mis-read action silently corrupts every
        adjusted price before its ex-date.
        """
        ...
