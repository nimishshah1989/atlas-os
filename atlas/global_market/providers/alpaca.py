"""Alpaca adapter — Market Data daily bars (SIP feed) + Trading-API assets (identity flags).

Uses the official ``alpaca-py`` SDK, imported LAZILY inside the methods so this module
imports — and the pipeline type-checks — without the package (it lives in the ``[global]``
extra, not the default venv). Names verified against alpaca-py 0.44.0 on 2026-09-04:
``StockHistoricalDataClient.get_stock_bars(StockBarsRequest)`` → ``BarSet.data``
(``dict[symbol, list[Bar]]``; Bar = timestamp/open/high/low/close/volume/trade_count/vwap),
``Adjustment.{RAW,SPLIT,ALL}``, ``DataFeed.SIP``, ``TimeFrame.Day``,
``TradingClient(paper=True).get_all_assets(GetAssetsRequest(status, asset_class))`` →
``Asset`` (id/symbol/name/exchange/asset_class/tradable/fractionable).

Free-plan rules baked in:
* SIP history must be older than 15 minutes → ``end`` is clamped to ``now − 16 min``.
* 200 requests/minute → the min-interval limiter from ``scripts/foundation/ingest_kite.py``
  (it spaces OUR calls; the SDK's own page loop inside one call is not spaced).
* Pagination is the SDK's: ``get_stock_bars`` walks ``page_token`` at 10,000 bars/page.
  We deliberately do NOT pass ``limit`` — in the SDK it caps the TOTAL bars per call
  (``RESTClient._get_marketdata``: ``actual_limit = min(limit − total_items, page_limit)``)
  and would silently truncate a multi-year backfill. Missing rows are a rule-#0 failure.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from atlas.global_market.calendar import NEW_YORK
from atlas.global_market.providers.base import (
    ASSET_COLUMNS,
    BAR_COLUMNS,
    Adjustment,
    CallCounter,
)

FEED = "sip"
SYMBOLS_PER_REQUEST = 200
FREE_PLAN_DELAY = timedelta(minutes=16)  # "no SIP data newer than 15 min" + 1 min margin
MIN_INTERVAL_S = 0.31  # ≥0.31 s between request STARTS ≈ 193/min (Alpaca cap 200/min)
_SDK_ADJUSTMENT: dict[str, str] = {"raw": "RAW", "split": "SPLIT", "all": "ALL"}


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _enum_value(x: object) -> str:
    return str(getattr(x, "value", x))


def _empty(columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in columns})


def clamp_end(end: date, now: datetime) -> datetime:
    """End-of-``end`` in New York, clamped to ``now − FREE_PLAN_DELAY`` (UTC, tz-aware)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clamp_end: `now` must be tz-aware (rule #5)")
    end_ny = datetime.combine(end, dtime.max, tzinfo=ZoneInfo(NEW_YORK)).astimezone(UTC)
    return min(end_ny, now.astimezone(UTC) - FREE_PLAN_DELAY)


class AlpacaProvider:
    """``PriceProvider`` + ``AssetProvider`` over Alpaca's free plan (paper account)."""

    name = "alpaca"

    def __init__(
        self,
        keys: tuple[str, str] | None = None,
        counter: CallCounter | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._keys = keys  # resolved lazily: constructing the adapter never touches env
        self.counter = counter or CallCounter(self.name)
        self._now = now or (lambda: datetime.now(UTC))
        self._last_call = 0.0

    def _creds(self) -> tuple[str, str]:
        if self._keys is None:
            from atlas.global_market.config import alpaca_keys

            self._keys = alpaca_keys()
        return self._keys

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
        adjustment: Adjustment = "all",
    ) -> pd.DataFrame:
        from alpaca.data.enums import (  # pyright: ignore[reportMissingImports]
            Adjustment as SdkAdjustment,
        )
        from alpaca.data.enums import DataFeed  # pyright: ignore[reportMissingImports]
        from alpaca.data.historical import (  # pyright: ignore[reportMissingImports]
            StockHistoricalDataClient,
        )
        from alpaca.data.requests import StockBarsRequest  # pyright: ignore[reportMissingImports]
        from alpaca.data.timeframe import TimeFrame  # pyright: ignore[reportMissingImports]

        if adjustment not in _SDK_ADJUSTMENT:
            raise ValueError(
                f"adjustment must be one of {sorted(_SDK_ADJUSTMENT)}, got {adjustment!r}"
            )
        key, secret = self._creds()
        client = StockHistoricalDataClient(key, secret)
        ny = ZoneInfo(NEW_YORK)
        start_dt = datetime.combine(start, dtime.min, tzinfo=ny)
        end_dt = clamp_end(end, self._now())
        if end_dt < start_dt:
            return _empty(BAR_COLUMNS)

        frames: list[pd.DataFrame] = []
        for chunk in _chunks(list(dict.fromkeys(symbols)), SYMBOLS_PER_REQUEST):
            req = StockBarsRequest(
                symbol_or_symbols=chunk,
                start=start_dt,
                end=end_dt,
                timeframe=TimeFrame.Day,
                adjustment=SdkAdjustment[_SDK_ADJUSTMENT[adjustment]],
                feed=DataFeed.SIP,
            )
            self._rate_limit()
            try:
                barset = client.get_stock_bars(req)
            except Exception:
                self.counter.record("stocks/bars", ok=False, note=f"{len(chunk)} symbols")
                raise
            frame = _barset_to_frame(barset, ny)
            self.counter.record("stocks/bars", n_rows=len(frame), note=f"{len(chunk)} symbols")
            frames.append(frame)
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

        key, secret = self._creds()
        client = TradingClient(key, secret, paper=True)  # paper base URL is the SDK default
        self._rate_limit()
        try:
            raw = client.get_all_assets(
                GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
            )
        except Exception:
            self.counter.record("assets", ok=False)
            raise
        rows = [
            (
                a.symbol,
                a.name,
                _enum_value(a.exchange),
                _enum_value(a.asset_class),
                bool(a.tradable),
                bool(a.fractionable),
                str(a.id),
            )
            for a in raw
        ]
        self.counter.record("assets", n_rows=len(rows))
        if not rows:
            return _empty(ASSET_COLUMNS)
        return pd.DataFrame.from_records(rows, columns=list(ASSET_COLUMNS)).sort_values(
            by="symbol", ignore_index=True
        )


def _barset_to_frame(barset: Any, tz: ZoneInfo) -> pd.DataFrame:
    """SDK ``BarSet`` → the Protocol frame. ``date`` = the bar timestamp's New York date.

    ``barset`` is ``Any`` because the SDK is an optional extra: its ``BarSet``/``Bar``
    models (fields verified in the module docstring) are not importable at type-check time.
    """
    data: dict[str, list[Any]] = barset.data or {}
    rows = []
    for symbol, bars in data.items():
        for b in bars:
            ts: datetime = b.timestamp
            rows.append(
                (
                    symbol,
                    ts.astimezone(tz).date(),
                    b.open,
                    b.high,
                    b.low,
                    b.close,
                    int(b.volume),
                    b.trade_count,
                    b.vwap,
                )
            )
    if not rows:
        return _empty(BAR_COLUMNS)
    return pd.DataFrame.from_records(rows, columns=list(BAR_COLUMNS))
