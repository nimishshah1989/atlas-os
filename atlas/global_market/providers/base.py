"""Provider Protocols + the call counter every adapter reports through.

Three structural Protocols (prices, assets, holdings) define the DataFrame shapes the
pipeline scripts consume; adapters (alpaca, stooq_bulk, fred, edgar, issuer_holdings) do
the I/O. Selected at runtime by ``GLOBAL_PRICE_PROVIDER`` (``config.price_provider()``).

``CallCounter`` only COUNTS. The free tiers are a monitored budget, so pipeline scripts
turn its ``calls`` into ``atlas_global.provider_calls`` rows — the write happens in the
script, never here (adapters stay I/O-in, DataFrame-out).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, Protocol, runtime_checkable

import pandas as pd

Adjustment = Literal["raw", "split", "all"]

# Column contracts. Prices are as delivered by the provider (raw, split- or all-adjusted
# per the request); ``date`` is the exchange-local (New York) calendar date of the bar.
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
# ``weight_frac`` is a FRACTION, always (Σ ≈ 1 for an unleveraged fund) — the name carries
# the unit so a percent can never sneak in unnoticed.
HOLDING_COLUMNS: tuple[str, ...] = (
    "holding_key",
    "weight_frac",
    "market_value_usd",
    "country_iso2",
    "asset_category",
    "as_of_date",
)


@runtime_checkable
class PriceProvider(Protocol):
    """Daily bars for many symbols over a date range."""

    name: str

    def bars(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        adjustment: Adjustment,
    ) -> pd.DataFrame:
        """One row per (symbol, session) with :data:`BAR_COLUMNS`; empty frame when none."""
        ...


@runtime_checkable
class AssetProvider(Protocol):
    """The provider's tradable universe (identity flags, not prices)."""

    name: str

    def assets(self) -> pd.DataFrame:
        """One row per asset with :data:`ASSET_COLUMNS`."""
        ...


@runtime_checkable
class HoldingsProvider(Protocol):
    """Portfolio holdings of one fund as of a date."""

    name: str

    def holdings(self, symbol: str, as_of: date | None) -> pd.DataFrame:
        """One row per holding with :data:`HOLDING_COLUMNS`; ``as_of=None`` = latest."""
        ...


@dataclass(frozen=True, slots=True)
class ProviderCall:
    """One request against a provider endpoint, as the pipeline will journal it."""

    provider: str
    endpoint: str
    at: datetime  # tz-aware UTC
    n_rows: int
    ok: bool
    note: str = ""


class CallCounter:
    """In-process tally of provider requests. Count only — scripts persist it.

    >>> c = CallCounter("alpaca")
    >>> _ = c.record("stocks/bars", n_rows=120)
    >>> c.count(), c.count("stocks/bars"), c.count("assets")
    (1, 1, 0)
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self._calls: list[ProviderCall] = []

    def record(
        self, endpoint: str, *, n_rows: int = 0, ok: bool = True, note: str = ""
    ) -> ProviderCall:
        call = ProviderCall(
            provider=self.provider,
            endpoint=endpoint,
            at=datetime.now(UTC),
            n_rows=n_rows,
            ok=ok,
            note=note,
        )
        self._calls.append(call)
        return call

    @property
    def calls(self) -> tuple[ProviderCall, ...]:
        return tuple(self._calls)

    def count(self, endpoint: str | None = None) -> int:
        if endpoint is None:
            return len(self._calls)
        return sum(1 for c in self._calls if c.endpoint == endpoint)

    def rows(self, endpoint: str | None = None) -> int:
        return sum(c.n_rows for c in self._calls if endpoint is None or c.endpoint == endpoint)
