"""KiteConnect WebSocket ingester — bar aggregation, EMA, RS, persistence.

Architecture:
- KiteTicker(threaded=True) fires on_ticks in a background thread.
- on_ticks puts raw tick dicts onto a queue.Queue (non-blocking, thread-safe).
- _bar_close_loop runs in a second thread, sleeps to the next IST :00/:15/:30/:45
  boundary, drains the queue, aggregates OHLCV, computes EMA + RS, upserts.
- EMA state and open prices are held in instance dicts; no external state store.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time as _time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import structlog

from atlas.intraday.ema_engine import EMAState, bootstrap_ema_state, update_ema
from atlas.intraday.persistence import BarRecord, upsert_bars
from atlas.intraday.rs_engine import (
    NIFTY50_TOKEN,
    compute_return_since_open,
    compute_rs,
)

log = structlog.get_logger()

# IST timezone
_IST = timezone(timedelta(hours=5, minutes=30))

# 15-min boundary minutes
_BAR_MINUTES = {0, 15, 30, 45}

# Market open time (09:15 IST) — open prices are reset at this time each day
_MARKET_OPEN_HOUR = 9
_MARKET_OPEN_MINUTE = 15

# Token map cache file path
_TOKEN_CACHE_PATH = Path.home() / ".kite_token_map.json"
_TOKEN_CACHE_MAX_AGE_SECONDS = 86_400  # 24 hours


def _strip_dialect(conn_str: str) -> str:
    """Strip SQLAlchemy dialect prefix for raw psycopg2 connections."""
    if conn_str.startswith("postgresql+psycopg2://"):
        return conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)
    return conn_str


class IntradayIngester:
    """Orchestrates KiteConnect WebSocket ingest → bar aggregation → DB persist.

    Usage::

        ingester = IntradayIngester(conn_str=Config.assert_db_url())
        ingester.start()
        # ... runs until Ctrl-C or ingester.stop() ...
        ingester.stop()
    """

    def __init__(self, conn_str: str) -> None:
        self._conn_str = conn_str

        # Thread-safe queue: ticks flow from on_ticks → _bar_close_loop
        self._tick_queue: queue.Queue[dict] = queue.Queue()

        # Current OHLCV accumulator per instrument_token (int)
        # {token: {"open": Decimal, "high": Decimal, "low": Decimal,
        #           "close": Decimal, "volume": int, "tick_count": int}}
        self._current_bar: dict[int, dict[str, Any]] = {}

        # EMA state: instrument_id (UUID str) → EMAState
        self._ema_state: dict[str, EMAState] = {}

        # Open prices for RS computation: instrument_id str → Decimal
        self._open_prices: dict[str, Decimal] = {}

        # Token map: kite instrument_token (int) → atlas instrument_id str
        # Special key "NIFTY50_INDEX" for the Nifty 50 benchmark
        self._token_map: dict[int, str] = {}

        self._kite: Any = None  # KiteConnect REST instance
        self._ticker: Any = None  # KiteTicker instance

        self._bar_close_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # Serialise bar-close processing so stop() and _bar_close_loop cannot
        # concurrently enter _process_bar_close for the same bar_time.
        self._bar_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Bootstrap EMA, load token map, connect ticker, start bar-close thread."""
        log.info("ingester_starting")

        # 1. Bootstrap EMA state from last nightly run
        self._ema_state = bootstrap_ema_state(conn_str=self._conn_str)

        # 2. Load instrument token map
        self._token_map = self._load_token_map()
        log.info(
            "token_map_loaded",
            instrument_count=len(self._token_map) - 1,  # exclude NIFTY50_INDEX
        )

        # 3. Connect KiteTicker
        self._connect_ticker()

        # 4. Start bar-close processing thread
        self._bar_close_thread = threading.Thread(
            target=self._bar_close_loop,
            name="bar-close-loop",
            daemon=True,
        )
        self._bar_close_thread.start()
        log.info("ingester_started")

    def stop(self) -> None:
        """Graceful shutdown: flush current bar, write EOD sentinel, disconnect."""
        log.info("ingester_stopping")
        self._stop_event.set()

        # Flush whatever partial bar data we have
        self._flush_current_bars(reason="shutdown")

        # Write EOD sentinel to signal nightly compute job
        self._write_eod_sentinel()

        if self._ticker is not None:
            try:
                self._ticker.stop()
            except Exception as exc:
                log.warning("ticker_stop_error", error=str(exc))

        if self._bar_close_thread and self._bar_close_thread.is_alive():
            self._bar_close_thread.join(timeout=10)

        log.info("ingester_stopped")

    # ------------------------------------------------------------------ #
    # Token map loading                                                    #
    # ------------------------------------------------------------------ #

    def _load_token_map(self) -> dict[int, str]:
        """Load KiteConnect instrument_token → atlas instrument_id (UUID str).

        1. Try cache file (~/.kite_token_map.json, refreshed daily).
        2. If stale or missing: call kite.instruments("NSE") + match to universe.
        3. Cache result to file.
        Returns dict mapping int token → UUID str (+ NIFTY50_INDEX sentinel).
        """
        # Check cache freshness
        if _TOKEN_CACHE_PATH.exists():
            try:
                cache_data = json.loads(_TOKEN_CACHE_PATH.read_text())
                cached_at = cache_data.get("cached_at", 0)
                age_seconds = _time.time() - float(cached_at)
                if age_seconds < _TOKEN_CACHE_MAX_AGE_SECONDS:
                    # Rebuild with int keys (JSON serialises all keys as strings)
                    token_map = {int(k): v for k, v in cache_data["token_map"].items()}
                    log.info(
                        "token_map_loaded_from_cache",
                        age_seconds=int(age_seconds),
                        count=len(token_map),
                    )
                    return token_map
            except Exception as exc:
                log.warning("token_cache_load_failed", error=str(exc))

        # Build fresh map
        token_map = self._build_token_map()

        # Cache to file
        try:
            cache_payload = {
                "cached_at": _time.time(),
                "token_map": {str(k): v for k, v in token_map.items()},
            }
            _TOKEN_CACHE_PATH.write_text(json.dumps(cache_payload))
            log.info("token_map_cached", path=str(_TOKEN_CACHE_PATH))
        except Exception as exc:
            log.warning("token_cache_write_failed", error=str(exc))

        return token_map

    def _build_token_map(self) -> dict[int, str]:
        """Build token → instrument_id map from KiteConnect + atlas universe."""
        # Load atlas universe symbols
        dsn = _strip_dialect(self._conn_str)
        conn = psycopg2.connect(dsn)  # type: ignore[attr-defined]
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT symbol, instrument_id::text
                    FROM atlas.atlas_universe_stocks
                    WHERE effective_to IS NULL
                    """
                )
                universe_rows = cur.fetchall()
        finally:
            conn.close()

        symbol_to_id: dict[str, str] = {row[0]: row[1] for row in universe_rows}
        log.info("universe_loaded", count=len(symbol_to_id))

        # Fetch instruments from KiteConnect REST
        if self._kite is None:
            self._init_kite_rest()

        kite = self._kite
        assert kite is not None
        try:
            instruments = kite.instruments("NSE")
        except Exception as exc:
            log.warning("kite_instruments_fetch_failed", error=str(exc))
            instruments = []

        token_map: dict[int, str] = {}
        matched = 0
        for item in instruments:
            sym = item.get("tradingsymbol", "")
            token = item.get("instrument_token")
            if token and sym in symbol_to_id:
                token_map[int(token)] = symbol_to_id[sym]
                matched += 1

        # Always include Nifty50 benchmark token
        token_map[NIFTY50_TOKEN] = "NIFTY50_INDEX"

        log.info(
            "token_map_built",
            total_instruments=len(instruments),
            matched=matched,
        )
        return token_map

    # ------------------------------------------------------------------ #
    # KiteConnect helpers                                                  #
    # ------------------------------------------------------------------ #

    def _init_kite_rest(self) -> None:
        """Initialise KiteConnect REST client with access token from DB."""
        from kiteconnect import KiteConnect  # type: ignore[import-untyped]

        from atlas.intraday.auth import get_valid_access_token

        api_key = os.environ.get("KITE_API_KEY", "")
        if not api_key:
            raise ValueError("KITE_API_KEY environment variable not set")

        access_token = get_valid_access_token(conn_str=self._conn_str)
        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)

    def _connect_ticker(self) -> None:
        """Create and connect KiteTicker WebSocket."""
        from kiteconnect import KiteTicker  # type: ignore[import-untyped]

        from atlas.intraday.auth import get_valid_access_token

        api_key = os.environ.get("KITE_API_KEY", "")
        if not api_key:
            raise ValueError("KITE_API_KEY environment variable not set")

        access_token = get_valid_access_token(conn_str=self._conn_str)
        self._ticker = KiteTicker(api_key, access_token, threaded=True)

        self._ticker.on_ticks = self._on_ticks
        self._ticker.on_connect = self._on_connect
        self._ticker.on_reconnect = self._on_reconnect
        self._ticker.on_close = self._on_close
        self._ticker.on_error = self._on_error

        subscribe_tokens = list(self._token_map.keys())
        self._ticker.connect()
        # subscribe after connect event fires via on_connect
        self._pending_tokens = subscribe_tokens

    # ------------------------------------------------------------------ #
    # Ticker callbacks                                                     #
    # ------------------------------------------------------------------ #

    def _on_connect(self, ws: Any, _response: Any) -> None:
        """Subscribe to all tracked tokens on WebSocket connect."""
        tokens = getattr(self, "_pending_tokens", list(self._token_map.keys()))
        ws.subscribe(tokens)
        ws.set_mode(ws.MODE_FULL, tokens)
        log.info("ticker_connected", subscribed_tokens=len(tokens))

    def _on_ticks(self, _ws: Any, ticks: list[dict]) -> None:
        """Receive ticks from KiteTicker thread — enqueue, do NOT process here."""
        for tick in ticks:
            self._tick_queue.put_nowait(tick)

    def _on_reconnect(self, _ws: Any, attempts_count: int) -> None:
        """On reconnect, backfill current bar from REST quotes."""
        log.warning("ticker_reconnecting", attempts=attempts_count)
        if self._kite is None:
            return
        with self._bar_lock:
            try:
                tokens = list(self._token_map.keys())
                quotes: dict = self._kite.quote(tokens)
                for token_str, quote_data in quotes.items():
                    token = int(token_str)
                    ohlc = quote_data.get("ohlc", {})
                    last_price = quote_data.get("last_price")
                    if not last_price:
                        continue
                    close = Decimal(str(last_price))
                    open_val = Decimal(str(ohlc.get("open", last_price)))
                    high_val = Decimal(str(ohlc.get("high", last_price)))
                    low_val = Decimal(str(ohlc.get("low", last_price)))
                    volume = int(quote_data.get("volume", 0))

                    if token not in self._current_bar:
                        self._current_bar[token] = {
                            "open": open_val,
                            "high": high_val,
                            "low": low_val,
                            "close": close,
                            "volume": volume,
                            "tick_count": 1,
                        }
                    else:
                        bar = self._current_bar[token]
                        bar["close"] = close
                        bar["high"] = max(bar["high"], high_val)
                        bar["low"] = min(bar["low"], low_val)
                log.info("reconnect_backfill_complete", token_count=len(quotes))
            except Exception as exc:
                log.warning("reconnect_backfill_failed", error=str(exc))

    def _on_close(self, _ws: Any, code: Any, reason: Any) -> None:
        log.warning("ticker_closed", code=code, reason=reason)

    def _on_error(self, _ws: Any, code: Any, reason: Any) -> None:
        log.error("ticker_error", code=code, reason=reason)

    # ------------------------------------------------------------------ #
    # Bar-close processing loop                                            #
    # ------------------------------------------------------------------ #

    def _bar_close_loop(self) -> None:
        """Wall-clock aligned bar-close processor.

        Sleeps to the next :00/:15/:30/:45 IST boundary, drains the tick
        queue, builds OHLCV bars, computes EMA + RS, and upserts to DB.
        Loops until _stop_event is set.
        """
        while not self._stop_event.is_set():
            sleep_secs = self._seconds_to_next_boundary()
            log.debug("bar_close_sleeping", seconds=round(sleep_secs, 1))

            # Sleep in small increments so stop_event can interrupt
            deadline = _time.monotonic() + sleep_secs
            while _time.monotonic() < deadline:
                if self._stop_event.is_set():
                    return
                _time.sleep(min(1.0, deadline - _time.monotonic()))

            bar_time = self._current_bar_time()
            with self._bar_lock:
                self._process_bar_close(bar_time)

    def _current_bar_time(self) -> datetime:
        """Return the bar_time for the bar that just closed (IST aligned)."""
        now_ist = datetime.now(tz=_IST)
        # Round down to last :00/:15/:30/:45
        minute = (now_ist.minute // 15) * 15
        return now_ist.replace(minute=minute, second=0, microsecond=0)

    def _process_bar_close(self, bar_time: datetime) -> None:
        """Drain queue, aggregate OHLCV, compute derived metrics, upsert."""
        # Drain all queued ticks into current bar state
        self._drain_tick_queue()

        # Reset open prices at 09:15 IST (start of market)
        now_ist = datetime.now(tz=_IST)
        if now_ist.hour == _MARKET_OPEN_HOUR and now_ist.minute == _MARKET_OPEN_MINUTE:
            self._open_prices.clear()
            log.info("open_prices_reset", bar_time=bar_time.isoformat())

        # Compute Nifty50 return for RS denominator
        nifty_return: Decimal | None = None
        nifty_token = NIFTY50_TOKEN
        if nifty_token in self._current_bar:
            nifty_bar = self._current_bar[nifty_token]
            nifty_inst_id = self._token_map.get(nifty_token)
            if nifty_inst_id == "NIFTY50_INDEX":
                nifty_open = self._open_prices.get("NIFTY50_INDEX")
                if nifty_open is None:
                    nifty_open = nifty_bar["open"]
                    self._open_prices["NIFTY50_INDEX"] = nifty_open
                nifty_return = compute_return_since_open(nifty_bar["close"], nifty_open)

        # Build BarRecord list for all tracked stocks (exclude Nifty sentinel)
        bar_records: list[BarRecord] = []
        for token, bar_data in self._current_bar.items():
            inst_id_str = self._token_map.get(token)
            if inst_id_str is None or inst_id_str == "NIFTY50_INDEX":
                continue

            try:
                inst_uuid = uuid.UUID(inst_id_str)
            except ValueError:
                log.warning("invalid_instrument_id", token=token, value=inst_id_str)
                continue

            close = bar_data["close"]

            # Set open price if not already known (first bar of the day)
            if inst_id_str not in self._open_prices:
                self._open_prices[inst_id_str] = bar_data["open"]

            open_price = self._open_prices[inst_id_str]
            stock_return = compute_return_since_open(close, open_price)
            rs = compute_rs(stock_return, nifty_return)

            # EMA update
            if inst_id_str in self._ema_state:
                new_ema = update_ema(close, self._ema_state[inst_id_str])
            else:
                # Bootstrap: use close as seed for both EMAs
                new_ema = EMAState(ema_20=close, ema_50=close)
            self._ema_state[inst_id_str] = new_ema

            bar_records.append(
                BarRecord(
                    instrument_id=inst_uuid,
                    bar_time=bar_time,
                    open=bar_data.get("open"),
                    high=bar_data.get("high"),
                    low=bar_data.get("low"),
                    close=close,
                    volume=bar_data.get("volume"),
                    tick_count=bar_data.get("tick_count"),
                    ema_20=new_ema.ema_20,
                    ema_50=new_ema.ema_50,
                    rs_vs_nifty=rs,
                    gap_filled=False,
                )
            )

        # Upsert to DB
        n_upserted = 0
        if bar_records:
            n_upserted = upsert_bars(bar_records, conn_str=self._conn_str)

        log.info(
            "bar_close_processed",
            bar_time=bar_time.isoformat(),
            n_instruments=len(bar_records),
            n_upserted=n_upserted,
        )

        # Reset current bar accumulator for the next interval
        self._current_bar.clear()

    def _drain_tick_queue(self) -> None:
        """Drain all pending ticks from the queue into _current_bar."""
        drained = 0
        while True:
            try:
                tick = self._tick_queue.get_nowait()
                self._merge_tick(tick)
                drained += 1
            except queue.Empty:
                break
        if drained:
            log.debug("ticks_drained", count=drained)

    def _merge_tick(self, tick: dict) -> None:
        """Merge one tick into the current bar accumulator."""
        token = tick.get("instrument_token")
        if token is None:
            return
        if token not in self._token_map:
            return

        last_price = tick.get("last_price")
        if last_price is None:
            return

        close = Decimal(str(last_price))
        ohlc = tick.get("ohlc", {})

        if token not in self._current_bar:
            open_val = Decimal(str(ohlc.get("open", last_price)))
            self._current_bar[token] = {
                "open": open_val,
                "high": close,
                "low": close,
                "close": close,
                "volume": int(tick.get("volume", 0)),
                "tick_count": 1,
            }
        else:
            bar = self._current_bar[token]
            bar["close"] = close
            bar["high"] = max(bar["high"], close)
            bar["low"] = min(bar["low"], close)
            bar["volume"] = int(tick.get("volume", 0))
            bar["tick_count"] = bar["tick_count"] + 1

    def _flush_current_bars(self, reason: str = "flush") -> None:
        """Write current partial bars to DB (used on shutdown)."""
        with self._bar_lock:
            if not self._current_bar:
                return
            bar_time = self._current_bar_time()
            log.info("flushing_partial_bars", reason=reason, bar_time=bar_time.isoformat())
            self._process_bar_close(bar_time)

    # ------------------------------------------------------------------ #
    # IST boundary helpers                                                 #
    # ------------------------------------------------------------------ #

    def _seconds_to_next_boundary(self) -> float:
        """Return seconds until the next :00/:15/:30/:45 minute boundary in IST."""
        now_ist = datetime.now(tz=_IST)
        current_minute = now_ist.minute
        current_second = now_ist.second
        current_microsecond = now_ist.microsecond

        # Find next boundary minute
        for boundary in sorted(_BAR_MINUTES):
            if boundary > current_minute:
                next_minute = boundary
                break
        else:
            next_minute = 60  # rolls to :00 of next hour

        seconds_remaining = (
            (next_minute - current_minute) * 60 - current_second - current_microsecond / 1_000_000
        )
        return max(0.0, seconds_remaining)

    # ------------------------------------------------------------------ #
    # EOD sentinel                                                         #
    # ------------------------------------------------------------------ #

    def _write_eod_sentinel(self) -> None:
        """Insert a session_type='closed' row at 15:35 IST to signal EOD.

        The nightly compute job checks for this row to confirm intraday
        data collection is complete before running overnight metrics.
        The sentinel value is pgp_sym_encrypt'd so the column always holds
        a valid PGP blob — guards against accidental decrypt in future queries.
        """
        enc_key = os.environ.get("KITE_TOKEN_ENCRYPTION_KEY", "")
        if not enc_key:
            log.warning("eod_sentinel_skipped", reason="KITE_TOKEN_ENCRYPTION_KEY not set")
            return

        dsn = _strip_dialect(self._conn_str)
        try:
            conn = psycopg2.connect(dsn)  # type: ignore[attr-defined]
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO atlas.atlas_kite_session
                            (access_token_enc, session_type, expires_at)
                        VALUES (pgp_sym_encrypt('EOD-SENTINEL', %s), 'closed', NOW())
                        """,
                        (enc_key,),
                    )
            conn.close()
            log.info("eod_sentinel_written")
        except Exception as exc:
            log.warning("eod_sentinel_failed", error=str(exc))
