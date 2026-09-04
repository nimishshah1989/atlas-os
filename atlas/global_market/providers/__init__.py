"""Provider adapters — the ONLY off-box boundary of the US platform.

Each adapter implements a Protocol from :mod:`.base` and returns plain DataFrames; nothing
else in ``atlas.global_market`` makes a network call. Adapters are imported by module on
purpose (``from atlas.global_market.providers.alpaca import AlpacaProvider``) so importing
this package never pulls an optional SDK.
"""

from .base import (
    ASSET_COLUMNS,
    BAR_COLUMNS,
    HOLDING_COLUMNS,
    Adjustment,
    AssetProvider,
    CallCounter,
    HoldingsProvider,
    PriceProvider,
    ProviderCall,
)

__all__ = [
    "ASSET_COLUMNS",
    "BAR_COLUMNS",
    "HOLDING_COLUMNS",
    "Adjustment",
    "AssetProvider",
    "CallCounter",
    "HoldingsProvider",
    "PriceProvider",
    "ProviderCall",
]
