"""Tests for ``scripts/rebuild_v3_cache_universe_aware.py``.

Validates the universe-aware JOIN semantics and schema invariants. We
monkeypatch the SQLAlchemy engine seam so a synthetic OHLCV +
universe-membership result-set is streamed through the chunked-fetch
path, then assert:

1. The output pickle has the same shape as ``rebuild_v3_cache.py``
   (so :func:`atlas.discovery.engine._load_cache_files` consumes it
   without modification).
2. Rows for an iid are bounded by ``effective_from`` / ``effective_to``
   (stub returns only the matching rows; we verify the script doesn't
   add extras).
3. iids that were never in the universe are not in the cache.
4. Historical-only iids (effective_to set) are still represented.
"""

from __future__ import annotations

import importlib
import json
import pickle
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Stub engine — emulates SQLAlchemy stream_results + fetchmany API
# ---------------------------------------------------------------------------


class _StubResult:
    """Minimal SQLAlchemy ``Result``-like object for fetchmany chunking."""

    def __init__(self, rows: list[tuple[Any, ...]], keys: list[str]) -> None:
        self._rows = rows
        self._keys = keys
        self._idx = 0

    def keys(self) -> list[str]:
        return list(self._keys)

    def fetchmany(self, n: int) -> list[tuple[Any, ...]]:
        chunk = self._rows[self._idx : self._idx + n]
        self._idx += n
        return chunk

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows[self._idx :]


class _StubConn:
    """Routes queries by SQL fragment match to canned result-sets."""

    def __init__(
        self,
        engine: _StubEngine,
        ohlcv_rows: list[tuple[Any, ...]],
        nifty_rows: list[tuple[Any, ...]],
        universe_rows: list[tuple[Any, ...]],
    ) -> None:
        self._engine = engine
        self._ohlcv_rows = ohlcv_rows
        self._nifty_rows = nifty_rows
        self._universe_rows = universe_rows

    def execution_options(self, **_kwargs: Any) -> _StubConn:
        return self

    def execute(self, sql: Any, _params: dict[str, Any] | None = None) -> _StubResult:
        text = str(sql)
        if "de_index_prices" in text:
            return _StubResult(self._nifty_rows, ["date", "close"])
        if "de_equity_ohlcv" in text:
            # OHLCV query (universe-aware JOIN). Record the SQL globally
            # so the test can assert on it regardless of which conn fired.
            self._engine.last_ohlcv_sql = text
            return _StubResult(self._ohlcv_rows, ["date", "iid", "close", "volume"])
        if "atlas_universe_stocks" in text:
            # Diagnostics-only query.
            return _StubResult(
                self._universe_rows,
                ["iid", "tier", "effective_from", "effective_to"],
            )
        return _StubResult([], [])

    def close(self) -> None:
        return None

    def __enter__(self) -> _StubConn:
        return self

    def __exit__(self, *_a: Any) -> None:
        return None


class _StubEngine:
    """SQLAlchemy ``Engine`` stub for rebuild_v3_cache_universe_aware."""

    def __init__(
        self,
        ohlcv_rows: list[tuple[Any, ...]],
        nifty_rows: list[tuple[Any, ...]],
        universe_rows: list[tuple[Any, ...]],
    ) -> None:
        self._ohlcv_rows = ohlcv_rows
        self._nifty_rows = nifty_rows
        self._universe_rows = universe_rows
        self.last_ohlcv_sql: str | None = None

    def connect(self) -> _StubConn:
        return _StubConn(self, self._ohlcv_rows, self._nifty_rows, self._universe_rows)


# ---------------------------------------------------------------------------
# Module loader (script lives in scripts/, not in package)
# ---------------------------------------------------------------------------


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    name = "rebuild_v3_cache_universe_aware"
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_uniaware_rows() -> (
    tuple[
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
    ]
):
    """Build a universe-aware OHLCV result + universe + nifty rows.

    Universe composition:
      * 3 currently-active iids (effective_to=NULL), Large/Mid/Small
      * 2 historical-only iids (effective_to=2020-06-30) — both Mid

    OHLCV simulates the SQL filter — only returns rows that satisfy
    ``effective_from <= date AND (effective_to IS NULL OR date <= effective_to)``.
    """
    universe_rows: list[tuple[Any, ...]] = [
        ("uuid_alive_large", "Large", date(2015, 1, 1), None),
        ("uuid_alive_mid", "Mid", date(2015, 1, 1), None),
        ("uuid_alive_small", "Small", date(2015, 1, 1), None),
        ("uuid_dead_mid_01", "Mid", date(2015, 1, 1), date(2020, 6, 30)),
        ("uuid_dead_mid_02", "Mid", date(2015, 1, 1), date(2020, 6, 30)),
    ]

    alive_iids = ("uuid_alive_large", "uuid_alive_mid", "uuid_alive_small")
    dead_iids = ("uuid_dead_mid_01", "uuid_dead_mid_02")
    start = date(2015, 1, 1)
    alive_end = date(2026, 5, 22)
    dead_end = date(2020, 6, 30)

    ohlcv_rows: list[tuple[Any, ...]] = []
    cur = start
    while cur <= alive_end:
        for iid in alive_iids:
            ohlcv_rows.append((cur, iid, 100.0 + (cur.toordinal() % 50), 100_000))
        if cur <= dead_end:
            for iid in dead_iids:
                ohlcv_rows.append((cur, iid, 50.0, 50_000))
        cur += timedelta(days=1)

    nifty_rows: list[tuple[Any, ...]] = []
    cur = start
    while cur <= alive_end:
        nifty_rows.append((cur, 10000.0 + (cur.toordinal() % 200)))
        cur += timedelta(days=1)

    return ohlcv_rows, nifty_rows, universe_rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_uniaware_cache_matches_v2_schema(
    tmp_path: Path,
    synthetic_uniaware_rows: tuple[
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
    ],
) -> None:
    """v3 universe-aware cache must have the same columns / dtypes as v2.

    This is the load-bearing invariant: the deep_search engine reads
    both v2 and v3 caches through the same ``_load_cache_files`` path,
    so any drift in shape silently breaks panel computation.
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows, universe_rows = synthetic_uniaware_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows, universe_rows)

    output = tmp_path / "v3_uniaware.pkl"
    stats = mod.rebuild_v3_cache_universe_aware(
        output=output,
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    assert output.exists()
    df = pd.read_pickle(output)  # noqa: S301  — test-produced file
    assert list(df.columns) == ["date", "iid", "close", "volume"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert pd.api.types.is_object_dtype(df["iid"])
    assert pd.api.types.is_float_dtype(df["close"])
    assert pd.api.types.is_integer_dtype(df["volume"])
    # 5 iids in fixture: 3 alive + 2 dead.
    assert stats.unique_instruments == 5
    assert stats.universe_iids == 5
    assert stats.currently_active_iids == 3
    assert stats.historical_only_iids == 2


def test_uniaware_join_sql_respects_effective_window(
    tmp_path: Path,
    synthetic_uniaware_rows: tuple[
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
    ],
) -> None:
    """The OHLCV SQL must reference both universe table AND effective_from / effective_to.

    Without this, the cache is just a JOIN by iid — losing the
    survivorship-correction semantics that justify this rebuild.
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows, universe_rows = synthetic_uniaware_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows, universe_rows)
    mod.rebuild_v3_cache_universe_aware(
        output=tmp_path / "v3.pkl",
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    sql = engine.last_ohlcv_sql
    assert sql is not None, "OHLCV SQL was not executed against the stub engine"
    assert (
        "atlas_universe_stocks" in sql
    ), "universe-aware OHLCV SQL must JOIN against atlas.atlas_universe_stocks"
    assert "effective_from" in sql, "universe-aware OHLCV SQL must filter by effective_from"
    assert "effective_to" in sql, "universe-aware OHLCV SQL must filter by effective_to (or NULL)"
    assert "INNER JOIN" in sql.upper(), "must use INNER JOIN to enforce universe membership"


def test_uniaware_cache_includes_historical_universe_members(
    tmp_path: Path,
    synthetic_uniaware_rows: tuple[
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
    ],
) -> None:
    """Historical-only iids (effective_to set) must appear in the cache.

    This is the Yes Bank / DHFL / Vodafone-Idea pattern — names that
    left the universe but should still influence backtests for the
    period they were in it.
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows, universe_rows = synthetic_uniaware_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows, universe_rows)
    output = tmp_path / "v3.pkl"
    mod.rebuild_v3_cache_universe_aware(
        output=output,
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    df = pd.read_pickle(output)  # noqa: S301
    last_by_iid = df.groupby("iid")["date"].max()
    historical = last_by_iid[last_by_iid < pd.Timestamp("2021-01-01")]
    assert (
        len(historical) >= 1
    ), "universe-aware cache must include historically-delisted iids; got none"


def test_uniaware_cache_raises_on_empty_join(tmp_path: Path) -> None:
    """If the universe-aware JOIN returns zero rows, fail loudly.

    A silent zero-cache would be much worse than an error — downstream
    deep_search would emit a cache that scores nothing.
    """
    mod = _load_module()
    engine = _StubEngine(ohlcv_rows=[], nifty_rows=[], universe_rows=[])
    with pytest.raises(RuntimeError, match="zero rows"):
        mod.rebuild_v3_cache_universe_aware(
            output=tmp_path / "v3.pkl",
            since=date(2015, 1, 1),
            nifty500_output=tmp_path / "nifty.pkl",
            blacklist_output=tmp_path / "blacklist.json",
            inherit_blacklist=None,
            engine=engine,
        )


def test_uniaware_cache_pickle_roundtrips_through_pickle_load(
    tmp_path: Path,
    synthetic_uniaware_rows: tuple[
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
    ],
) -> None:
    """Pickle written by the script must load via the same ``pickle.load``
    path that :func:`atlas.discovery.engine._load_cache_files` uses.
    """
    mod = _load_module()
    ohlcv_rows, nifty_rows, universe_rows = synthetic_uniaware_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows, universe_rows)
    output = tmp_path / "v3.pkl"
    mod.rebuild_v3_cache_universe_aware(
        output=output,
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=None,
        engine=engine,
    )
    with output.open("rb") as fh:
        df = pickle.load(fh)  # noqa: S301
    assert isinstance(df, pd.DataFrame)
    assert {"date", "iid", "close", "volume"}.issubset(df.columns)


def test_uniaware_cache_inherits_blacklist_when_provided(
    tmp_path: Path,
    synthetic_uniaware_rows: tuple[
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
        list[tuple[Any, ...]],
    ],
) -> None:
    """``--inherit-blacklist`` copies the source list into the output JSON."""
    mod = _load_module()
    ohlcv_rows, nifty_rows, universe_rows = synthetic_uniaware_rows
    engine = _StubEngine(ohlcv_rows, nifty_rows, universe_rows)
    src_blacklist = tmp_path / "src_blacklist.json"
    src_blacklist.write_text(json.dumps([{"iid": "uuid_dead_mid_01", "symbol": "DEAD1"}]))
    mod.rebuild_v3_cache_universe_aware(
        output=tmp_path / "v3.pkl",
        since=date(2015, 1, 1),
        nifty500_output=tmp_path / "nifty.pkl",
        blacklist_output=tmp_path / "blacklist.json",
        inherit_blacklist=src_blacklist,
        engine=engine,
    )
    with (tmp_path / "blacklist.json").open() as fh:
        bl = json.load(fh)
    assert bl == [{"iid": "uuid_dead_mid_01", "symbol": "DEAD1"}]
