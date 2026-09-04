"""Alpaca adapter — Market Data daily bars (SIP feed) + Trading-API assets (identity flags).

Uses the official ``alpaca-py`` SDK, imported LAZILY inside the methods so this module
imports — and the pipeline type-checks — without the package (it lives in the ``[global]``
extra, not the default venv). Names verified against alpaca-py 0.44.0 on 2026-09-04:
``StockHistoricalDataClient.get_stock_bars(StockBarsRequest)`` → ``BarSet | dict`` (the
dict only when the client is built with ``raw_data=True``; refused here) with ``BarSet.data``
= ``dict[symbol, list[Bar]]`` and Bar = timestamp/open/high/low/close/volume/trade_count/vwap;
``Adjustment("raw"|"split"|"all")``, ``DataFeed.SIP``, ``TimeFrame(1, TimeFrameUnit.Day)``;
``TradingClient(paper=True).get_all_assets(GetAssetsRequest(status, asset_class))`` →
``list[Asset] | dict`` with Asset = id/symbol/name/exchange/asset_class/tradable/fractionable.

Free-plan rules baked in:
* SIP history must be older than 15 minutes → ``end`` is clamped to ``now − 16 min``.
* 200 requests/minute → the min-interval limiter from ``scripts/foundation/ingest_kite.py``
  (it spaces OUR calls; the SDK's own page loop inside one call is not spaced).
* Pagination is the SDK's: ``get_stock_bars`` walks ``page_token`` at 10,000 bars/page.
  We deliberately do NOT pass ``limit`` — in the SDK it caps the TOTAL bars per call
  (``RESTClient._get_marketdata``: ``actual_limit = min(limit − total_items, page_limit)``)
  and would silently truncate a multi-year backfill. Missing rows are a rule-#0 failure.

Prices cross the adapter boundary as ``Decimal`` (USD is money): ``Decimal(str(x))`` keeps
exactly the digits the JSON carried, where ``Decimal(x)`` would expose the float's binary
expansion. ``calls`` counts requests per endpoint — a failed request still counts, it spent
budget — and the pipeline script writes it to ``atlas_global.provider_calls``.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from decimal import Decimal
from itertools import batched
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

from atlas.global_market.calendar import NEW_YORK
from atlas.global_market.config import alpaca_keys
from atlas.global_market.providers.base import ASSET_COLUMNS, BAR_COLUMNS

if TYPE_CHECKING:
    from alpaca.data.models import BarSet  # pyright: ignore[reportMissingImports]

FEED = "sip"
SYMBOLS_PER_REQUEST = 200
FREE_PLAN_DELAY = timedelta(minutes=16)  # "no SIP data newer than 15 min" + 1 min margin
MIN_INTERVAL_S = 0.31  # ≥0.31 s between request STARTS ≈ 193/min (Alpaca cap 200/min)


def clamp_end(end: date, now: datetime) -> datetime:
    """End-of-``end`` in New York, clamped to ``now − FREE_PLAN_DELAY`` (UTC, tz-aware)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clamp_end: `now` must be tz-aware")
    end_ny = datetime.combine(end, dtime.max, tzinfo=ZoneInfo(NEW_YORK)).astimezone(UTC)
    return min(end_ny, now.astimezone(UTC) - FREE_PLAN_DELAY)


def _usd(x: float | None) -> Decimal | None:
    return None if x is None else Decimal(str(x))


def _empty(columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in columns})


class AlpacaProvider:
    """``PriceProvider`` + ``AssetProvider`` over Alpaca's free plan (paper account)."""

    name = "alpaca"

    def __init__(self, keys: tuple[str, str] | None = None) -> None:
        self._keys = keys or alpaca_keys()
        self.calls: Counter[str] = Counter()
        self._last_call = 0.0

    def _rate_limit(self) -> None:
        """Min-interval limiter (ingest_kite._rate_limit): spaces request STARTS."""
        gap = time.monotonic() - self._last_call
        if gap < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - gap)
        self._last_call = time.monotonic()

    def bars(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        adjustment: str = "all",
    ) -> pd.DataFrame:
        """Daily SIP bars; ``adjustment`` is a :data:`base.Adjustment` value (the SDK enum
        rejects anything else with ``ValueError``)."""
        from alpaca.data.enums import (  # pyright: ignore[reportMissingImports]
            Adjustment as SdkAdjustment,
        )
        from alpaca.data.enums import DataFeed  # pyright: ignore[reportMissingImports]
        from alpaca.data.historical import (  # pyright: ignore[reportMissingImports]
            StockHistoricalDataClient,
        )
        from alpaca.data.models import BarSet  # pyright: ignore[reportMissingImports]
        from alpaca.data.requests import StockBarsRequest  # pyright: ignore[reportMissingImports]
        from alpaca.data.timeframe import (  # pyright: ignore[reportMissingImports]
            TimeFrame,
            TimeFrameUnit,
        )

        key, secret = self._keys
        client = StockHistoricalDataClient(key, secret)
        ny = ZoneInfo(NEW_YORK)
        start_dt = datetime.combine(start, dtime.min, tzinfo=ny)
        end_dt = clamp_end(end, datetime.now(UTC))
        frames: list[pd.DataFrame] = []
        if end_dt >= start_dt:
            for chunk in batched(dict.fromkeys(symbols), SYMBOLS_PER_REQUEST):
                req = StockBarsRequest(
                    symbol_or_symbols=list(chunk),
                    start=start_dt,
                    end=end_dt,
                    # by value: the SDK annotates its enum members as plain `str`
                    timeframe=TimeFrame(1, TimeFrameUnit("Day")),
                    adjustment=SdkAdjustment(adjustment),
                    feed=DataFeed.SIP,
                )
                self._rate_limit()
                self.calls["stocks/bars"] += 1
                barset = client.get_stock_bars(req)
                if not isinstance(barset, BarSet):
                    raise TypeError("get_stock_bars returned raw data; a BarSet was expected")
                frames.append(_barset_to_frame(barset, ny))
        if not frames:
            return _empty(BAR_COLUMNS)
        return pd.concat(frames, ignore_index=True).sort_values(
            ["symbol", "date"], ignore_index=True
        )

    def assets(self) -> pd.DataFrame:
        """Active US equities (stocks AND ETFs) with Alpaca's tradable/fractionable flags."""
        from alpaca.trading.client import TradingClient  # pyright: ignore[reportMissingImports]
        from alpaca.trading.enums import (  # pyright: ignore[reportMissingImports]
            AssetClass,
            AssetStatus,
        )
        from alpaca.trading.requests import (  # pyright: ignore[reportMissingImports]
            GetAssetsRequest,
        )

        key, secret = self._keys
        client = TradingClient(key, secret, paper=True)  # paper base URL is the SDK default
        self._rate_limit()
        self.calls["assets"] += 1
        raw = client.get_all_assets(
            GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
        )
        if isinstance(raw, dict):
            raise TypeError("get_all_assets returned raw data; a list of Asset was expected")
        rows = [
            (
                a.symbol,
                a.name,
                a.exchange.value,
                a.asset_class.value,
                bool(a.tradable),
                bool(a.fractionable),
                str(a.id),
            )
            for a in raw
        ]
        if not rows:
            return _empty(ASSET_COLUMNS)
        return pd.DataFrame.from_records(rows, columns=list(ASSET_COLUMNS)).sort_values(
            by="symbol", ignore_index=True
        )


def _barset_to_frame(barset: BarSet, tz: ZoneInfo) -> pd.DataFrame:
    """SDK ``BarSet`` → the Protocol frame. ``date`` = the bar timestamp's New York date."""
    rows = [
        (
            symbol,
            b.timestamp.astimezone(tz).date(),
            _usd(b.open),
            _usd(b.high),
            _usd(b.low),
            _usd(b.close),
            int(b.volume),
            None if b.trade_count is None else int(b.trade_count),
            _usd(b.vwap),
        )
        for symbol, bars in (barset.data or {}).items()
        for b in bars
    ]
    if not rows:
        return _empty(BAR_COLUMNS)
    return pd.DataFrame.from_records(rows, columns=list(BAR_COLUMNS))
